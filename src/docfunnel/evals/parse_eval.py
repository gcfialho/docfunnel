"""Stage-level evaluation of the parse stage on the synthetic PDF set.

What is measured, per page, against ground truth from :mod:`docfunnel.synthetic_pdf`:

* **OCR routing**: precision, recall and accuracy of "this page needs OCR" (label:
  the page is a scanned image).
* **Text quality**: CER and WER after whitespace normalization, for digital pages
  and for scanned pages by noise level and OCR engine.
* **Field recall**: does the printed value of each labelled field appear in the
  parsed text of its gold page? This is what the LLM step can see at best.
* **Throughput**: text-layer pages/s in one process (pypdfium2 vs the ``pypdf``
  baseline, when installed), and the full pipeline in the page pool (pages/s,
  OCR pages/s, cold start, per-page OCR latency, peak worker memory). The hardware
  is recorded in the report because these numbers mean nothing without it.

``compare_parse_reports`` gates quality metrics in CI; throughput is reported but
not gated, except for one relative check inside the same job (pypdfium2 must stay
several times faster than pypdf on the same pages).
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import resource
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel

from docfunnel import __version__
from docfunnel.evals.compare import (
    Check,
    CheckResult,
    Comparison,
    Direction,
    Status,
    evaluate_check,
)
from docfunnel.evals.metrics import edit_counts, percentile, quote_found, safe_div
from docfunnel.evals.report import fmt_pct
from docfunnel.parse.model import ParsedDocument
from docfunnel.parse.ocr import resolve_engine_name
from docfunnel.parse.pipeline import (
    PagePool,
    ParseOptions,
    close_cached_pdfs,
    default_workers,
    parse_pdf_page,
)
from docfunnel.synthetic_pdf import DocTruth, load_manifest, manifest_sha256

# ---- report models -------------------------------------------------------------------


class Hardware(BaseModel):
    cpu: str
    logical_cores: int
    memory_gb: float | None
    os: str
    python: str


class ParseEvalMeta(BaseModel):
    run_name: str
    created_at: str
    package_version: str = __version__
    dataset: str
    dataset_sha256: str
    documents: int
    pages: int
    scanned_pages: dict[str, int]
    workers: int
    dpi: int
    versions: dict[str, str]
    hardware: Hardware


class RoutingMetrics(BaseModel):
    pages: int
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    precision: float | None
    recall: float | None
    accuracy: float
    by_route: dict[str, int]


class TextQuality(BaseModel):
    pages: int
    chars: int
    words: int
    cer: float | None
    wer: float | None


class FieldRecall(BaseModel):
    fields: int
    found: int
    recall: float | None


class PageRecord(BaseModel):
    doc_id: str
    page: int
    kind: str  # digital | scanned_light | scanned_heavy
    background: bool
    stray_text: bool
    route: str
    source: str
    cer: float | None
    wer: float | None
    total_ms: float


class EngineResult(BaseModel):
    engine: str
    quality: dict[str, TextQuality]  # by page kind, plus "scanned"
    field_recall: dict[str, FieldRecall]  # by page kind of the gold page, plus "all"
    pipeline_pages_per_s: float
    ocr_pages: int
    ocr_pages_per_s: float | None
    ocr_ms_p50: float | None
    ocr_ms_p95: float | None
    cold_start_s: float | None
    peak_worker_rss_mb: float | None
    page_errors: int
    pages: list[PageRecord]


class TextLayerBench(BaseModel):
    pages: int
    pypdfium2_pages_per_s: float
    pypdfium2_text_only_pages_per_s: float
    pypdf_pages_per_s: float | None
    speedup_vs_pypdf: float | None


class ParseEvalReport(BaseModel):
    meta: ParseEvalMeta
    routing: RoutingMetrics
    misrouted: list[PageRecord]
    text_layer: TextLayerBench
    engines: dict[str, EngineResult]

    def gate_metrics(self) -> dict[str, float | None]:
        metrics: dict[str, float | None] = {
            "routing_accuracy": self.routing.accuracy,
            "routing_precision": self.routing.precision,
            "routing_recall": self.routing.recall,
        }
        for name, result in self.engines.items():
            metrics[f"{name}.digital_cer"] = result.quality["digital"].cer
            metrics[f"{name}.scanned_cer"] = result.quality["scanned"].cer
            metrics[f"{name}.field_recall"] = result.field_recall["all"].recall
        return metrics


# ---- environment ---------------------------------------------------------------------


def _sysctl(name: str) -> str | None:
    try:
        return subprocess.run(
            ["sysctl", "-n", name], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def hardware_info() -> Hardware:
    cpu = platform.processor() or platform.machine()
    memory = None
    if sys.platform == "darwin":
        cpu = _sysctl("machdep.cpu.brand_string") or cpu
        raw = _sysctl("hw.memsize")
        memory = int(raw) / 2**30 if raw else None
    else:
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal"):
                    memory = int(line.split()[1]) / 2**20
                    break
        except OSError:
            pass
    return Hardware(
        cpu=cpu,
        logical_cores=os.cpu_count() or 1,
        memory_gb=round(memory, 1) if memory else None,
        os=f"{platform.system()} {platform.release()} ({platform.machine()})",
        python=platform.python_version(),
    )


def package_versions() -> dict[str, str]:
    found = {}
    for name in ("pypdfium2", "rapidocr", "onnxruntime", "pytesseract", "pypdf", "reportlab"):
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            continue
    try:
        import pytesseract

        found["tesseract"] = str(pytesseract.get_tesseract_version())
    except Exception:  # binary or wrapper missing
        pass
    return found


def _peak_child_rss_mb() -> float | None:
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if not rss:
        return None
    return round(rss / 2**20 if sys.platform == "darwin" else rss / 2**10, 1)


# ---- scoring ---------------------------------------------------------------------------


def page_kind(scanned: bool, noise: str | None) -> str:
    return f"scanned_{noise}" if scanned else "digital"


@dataclass
class _Accumulator:
    pages: int = 0
    char_edits: int = 0
    chars: int = 0
    word_edits: int = 0
    words: int = 0

    def add(self, counts: tuple[int, int, int, int]) -> None:
        self.pages += 1
        self.char_edits += counts[0]
        self.chars += counts[1]
        self.word_edits += counts[2]
        self.words += counts[3]

    def result(self) -> TextQuality:
        return TextQuality(
            pages=self.pages,
            chars=self.chars,
            words=self.words,
            cer=safe_div(self.char_edits, self.chars),
            wer=safe_div(self.word_edits, self.words),
        )


def score_routing(truths: Sequence[DocTruth], docs: Sequence[ParsedDocument]) -> RoutingMetrics:
    tp = fp = fn = tn = 0
    by_route: dict[str, int] = {}
    for truth, doc in zip(truths, docs, strict=True):
        for label, page in zip(truth.pages, doc.pages, strict=True):
            by_route[page.route] = by_route.get(page.route, 0) + 1
            if page.needs_ocr and label.scanned:
                tp += 1
            elif page.needs_ocr:
                fp += 1
            elif label.scanned:
                fn += 1
            else:
                tn += 1
    total = tp + fp + fn + tn
    return RoutingMetrics(
        pages=total,
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
        precision=safe_div(tp, tp + fp),
        recall=safe_div(tp, tp + fn),
        accuracy=(tp + tn) / total if total else 0.0,
        by_route=dict(sorted(by_route.items())),
    )


def score_engine(
    truths: Sequence[DocTruth], docs: Sequence[ParsedDocument]
) -> tuple[dict[str, TextQuality], dict[str, FieldRecall], list[PageRecord]]:
    quality: dict[str, _Accumulator] = {}
    recall: dict[str, list[int]] = {}
    records = []
    for truth, doc in zip(truths, docs, strict=True):
        if len(doc.pages) != len(truth.pages):
            raise ValueError(
                f"{truth.id}: parsed {len(doc.pages)} pages, expected {len(truth.pages)}"
            )
        for label, page in zip(truth.pages, doc.pages, strict=True):
            kind = page_kind(label.scanned, label.noise)
            counts = edit_counts(label.text, page.text)
            for key in (kind, "scanned") if label.scanned else (kind,):
                quality.setdefault(key, _Accumulator()).add(counts)
            records.append(
                PageRecord(
                    doc_id=truth.id,
                    page=page.number,
                    kind=kind,
                    background=label.background,
                    stray_text=bool(label.stray_text),
                    route=page.route,
                    source=page.source,
                    cer=safe_div(counts[0], counts[1]),
                    wer=safe_div(counts[2], counts[3]),
                    total_ms=page.timings_ms.get("total", 0.0),
                )
            )
        for fld in truth.fields:
            gold = truth.pages[fld.page - 1]
            hit = int(quote_found(fld.quote, doc.pages[fld.page - 1].text))
            for key in (page_kind(gold.scanned, gold.noise), "all"):
                bucket = recall.setdefault(key, [0, 0])
                bucket[0] += hit
                bucket[1] += 1
    for key in ("digital", "scanned"):
        quality.setdefault(key, _Accumulator())
    recall.setdefault("all", [0, 0])
    return (
        {key: acc.result() for key, acc in sorted(quality.items())},
        {
            key: FieldRecall(fields=total, found=found, recall=safe_div(found, total))
            for key, (found, total) in sorted(recall.items())
        },
        records,
    )


# ---- benchmarks ------------------------------------------------------------------------


def _best_of(repeats: int, run: Callable[[], None]) -> float:
    best = float("inf")
    for _ in range(repeats):
        started = time.perf_counter()
        run()
        best = min(best, time.perf_counter() - started)
    return best


def bench_text_layer(pages: Sequence[tuple[Path, int]], repeats: int = 3) -> TextLayerBench:
    """Single-process text extraction over the same digital pages, best of ``repeats``."""
    import pypdfium2 as pdfium

    by_file: dict[Path, list[int]] = {}
    for path, index in pages:
        by_file.setdefault(path, []).append(index)
    options = ParseOptions(ocr_engine="none")

    def full() -> None:
        for path, indexes in by_file.items():
            for index in indexes:
                parse_pdf_page(str(path), index, path.stem, options)
            close_cached_pdfs()

    def text_only() -> None:
        for path, indexes in by_file.items():
            pdf = pdfium.PdfDocument(str(path))
            for index in indexes:
                textpage = pdf[index].get_textpage()
                textpage.get_text_range()
                textpage.close()
            pdf.close()

    pypdf_rate = None
    try:
        from pypdf import PdfReader

        def with_pypdf() -> None:
            for path, indexes in by_file.items():
                reader = PdfReader(path)
                for index in indexes:
                    reader.pages[index].extract_text()

        pypdf_rate = len(pages) / _best_of(repeats, with_pypdf)
    except ImportError:
        pass
    full()  # warm-up: imports, PDFium initialisation
    full_rate = len(pages) / _best_of(repeats, full)
    text_rate = len(pages) / _best_of(repeats, text_only)
    return TextLayerBench(
        pages=len(pages),
        pypdfium2_pages_per_s=round(full_rate, 1),
        pypdfium2_text_only_pages_per_s=round(text_rate, 1),
        pypdf_pages_per_s=round(pypdf_rate, 1) if pypdf_rate else None,
        speedup_vs_pypdf=round(text_rate / pypdf_rate, 1) if pypdf_rate else None,
    )


@dataclass
class ParseEvalConfig:
    dataset: Path
    engines: list[str] = field(default_factory=lambda: ["auto"])
    workers: int | None = None
    dpi: int = 200
    run_name: str | None = None
    bench_repeats: int = 3


def run_parse_eval(config: ParseEvalConfig) -> ParseEvalReport:
    truths = load_manifest(config.dataset)
    paths = [config.dataset / t.file for t in truths]
    workers = config.workers or default_workers()
    digital_pages = [
        (config.dataset / t.file, p.number - 1) for t in truths for p in t.pages if not p.scanned
    ]
    text_layer = bench_text_layer(digital_pages, repeats=config.bench_repeats)

    engine_names = []
    for name in config.engines:
        resolved = resolve_engine_name(name) or "none"
        if resolved not in engine_names:
            engine_names.append(resolved)

    results: dict[str, EngineResult] = {}
    routing: RoutingMetrics | None = None
    misrouted: list[PageRecord] = []
    for name in engine_names:
        options = ParseOptions(ocr_engine=name, dpi=config.dpi)
        with PagePool(options, workers) as pool:
            started = time.perf_counter()
            docs = pool.parse(paths, [t.id for t in truths])
            elapsed = time.perf_counter() - started
            cold_start = pool.cold_start_s
        quality, recall, records = score_engine(truths, docs)
        if routing is None:
            routing = score_routing(truths, docs)
            scanned = {(t.id, p.number) for t in truths for p in t.pages if p.scanned}
            misrouted = [
                r
                for r in records
                if (r.route.startswith("ocr:")) != ((r.doc_id, r.page) in scanned)
            ]
        ocr_pages = [p for d in docs for p in d.pages if p.source == "ocr"]
        ocr_ms = [p.timings_ms["ocr"] for p in ocr_pages if "ocr" in p.timings_ms]
        total_pages = sum(len(d.pages) for d in docs)
        engine_label = next((p.ocr_engine for p in ocr_pages if p.ocr_engine), name)
        results[name] = EngineResult(
            engine=engine_label,
            quality=quality,
            field_recall=recall,
            pipeline_pages_per_s=round(total_pages / elapsed, 2),
            ocr_pages=len(ocr_pages),
            ocr_pages_per_s=round(len(ocr_pages) / elapsed, 2) if ocr_pages else None,
            ocr_ms_p50=round(v, 1) if (v := percentile(ocr_ms, 50)) is not None else None,
            ocr_ms_p95=round(v, 1) if (v := percentile(ocr_ms, 95)) is not None else None,
            cold_start_s=cold_start,
            peak_worker_rss_mb=_peak_child_rss_mb(),
            page_errors=sum(
                1 for d in docs for p in d.pages if p.error and not p.error.startswith("OCR needed")
            ),
            pages=records,
        )
    assert routing is not None
    scanned_counts: dict[str, int] = {}
    for t in truths:
        for p in t.pages:
            if p.scanned:
                scanned_counts[p.noise or "?"] = scanned_counts.get(p.noise or "?", 0) + 1
    meta = ParseEvalMeta(
        run_name=config.run_name or "+".join(engine_names),
        created_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        dataset=config.dataset.as_posix(),
        dataset_sha256=manifest_sha256(config.dataset),
        documents=len(truths),
        pages=sum(len(t.pages) for t in truths),
        scanned_pages=dict(sorted(scanned_counts.items())),
        workers=workers,
        dpi=config.dpi,
        versions=package_versions(),
        hardware=hardware_info(),
    )
    return ParseEvalReport(
        meta=meta, routing=routing, misrouted=misrouted, text_layer=text_layer, engines=results
    )


# ---- reporting -------------------------------------------------------------------------


def _rate(value: float | None, unit: str = "pages/s") -> str:
    return "n/a" if value is None else f"{value:,.1f} {unit}"


def summary_rows(report: ParseEvalReport) -> list[tuple[str, str]]:
    r = report.routing
    tl = report.text_layer
    rows = [
        ("Documents / pages", f"{report.meta.documents} / {report.meta.pages}"),
        (
            "OCR routing accuracy / precision / recall",
            f"{fmt_pct(r.accuracy)} / {fmt_pct(r.precision)} / {fmt_pct(r.recall)}",
        ),
        (
            "Raw text extraction, 1 process: pypdfium2 / pypdf",
            f"{_rate(tl.pypdfium2_text_only_pages_per_s)} / {_rate(tl.pypdf_pages_per_s)}"
            + (f" ({tl.speedup_vs_pypdf:.1f}x)" if tl.speedup_vs_pypdf else ""),
        ),
    ]
    for name, e in report.engines.items():
        q = e.quality
        rows += [
            (
                f"[{name}] CER digital / scanned light / heavy",
                " / ".join(
                    fmt_pct(q[k].cer) if k in q else "n/a"
                    for k in ("digital", "scanned_light", "scanned_heavy")
                ),
            ),
            (
                f"[{name}] WER scanned light / heavy",
                " / ".join(
                    fmt_pct(q[k].wer) if k in q else "n/a"
                    for k in ("scanned_light", "scanned_heavy")
                ),
            ),
            (
                f"[{name}] field recall digital / scanned light / heavy",
                " / ".join(
                    fmt_pct(e.field_recall[k].recall) if k in e.field_recall else "n/a"
                    for k in ("digital", "scanned_light", "scanned_heavy")
                ),
            ),
            (
                f"[{name}] pipeline, {report.meta.workers} workers: all pages / OCR pages",
                f"{_rate(e.pipeline_pages_per_s)} / {_rate(e.ocr_pages_per_s)}",
            ),
        ]
    return rows


def render_parse_markdown(report: ParseEvalReport) -> str:
    meta = report.meta
    hw = meta.hardware
    scanned = ", ".join(f"{v} {k}" for k, v in meta.scanned_pages.items())
    lines = [
        f"# Parse evaluation report: {meta.run_name}",
        "",
        f"- Dataset: `{meta.dataset}` (manifest sha256 `{meta.dataset_sha256[:12]}`): "
        f"{meta.documents} documents, {meta.pages} pages ({scanned} scanned)",
        f"- Hardware: {hw.cpu}, {hw.logical_cores} logical cores, "
        f"{hw.memory_gb or '?'} GB RAM, {hw.os}, Python {hw.python}",
        f"- Versions: {', '.join(f'{k} {v}' for k, v in meta.versions.items())}",
        f"- Page pool: {meta.workers} worker processes; OCR render at {meta.dpi} dpi",
        f"- Package `{meta.package_version}`, created {meta.created_at}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        *(f"| {name} | {value} |" for name, value in summary_rows(report)),
        "",
        "## OCR routing",
        "",
        "Label: the page is a scanned image. Prediction: the route starts with `ocr:`.",
        "",
        "| | Labelled scanned | Labelled digital |",
        "| --- | ---: | ---: |",
        f"| Routed to OCR | {report.routing.true_positive} | {report.routing.false_positive} |",
        f"| Kept text layer | {report.routing.false_negative} | {report.routing.true_negative} |",
        "",
        "| Route | Pages |",
        "| --- | ---: |",
        *(f"| `{k}` | {v} |" for k, v in report.routing.by_route.items()),
        "",
    ]
    if report.misrouted:
        lines += [
            "Misrouted pages:",
            "",
            "| Page | Kind | Full-page image | Route |",
            "| --- | --- | --- | --- |",
            *(
                f"| {r.doc_id} p{r.page} | {r.kind} | {'yes' if r.background else 'no'} "
                f"| `{r.route}` |"
                for r in report.misrouted
            ),
            "",
        ]
    lines += [
        "## Text quality (CER / WER after whitespace normalization)",
        "",
        "| Engine | Pages | Kind | CER | WER |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for name, e in report.engines.items():
        for kind, q in e.quality.items():
            lines.append(f"| {name} | {q.pages} | {kind} | {fmt_pct(q.cer)} | {fmt_pct(q.wer)} |")
    lines += [
        "",
        "## Field recall (printed value found on its gold page)",
        "",
        "| Engine | Gold page kind | Fields | Found | Recall |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for name, e in report.engines.items():
        for kind, fr in e.field_recall.items():
            lines.append(f"| {name} | {kind} | {fr.fields} | {fr.found} | {fmt_pct(fr.recall)} |")
    tl = report.text_layer
    lines += [
        "",
        "## Throughput",
        "",
        f"Text layer, single process, {tl.pages} digital pages, best of 3:",
        "",
        "| Extractor | Pages/s |",
        "| --- | ---: |",
        "| pypdfium2: text + OCR decision + line blocks with boxes "
        f"| {tl.pypdfium2_pages_per_s:,.1f} |",
        f"| pypdfium2: raw text only | {tl.pypdfium2_text_only_pages_per_s:,.1f} |",
        f"| pypdf `extract_text()` (previous loader) | {_rate(tl.pypdf_pages_per_s, '')} |",
        "",
        f"Full pipeline in the page pool ({meta.workers} processes, one thread each):",
        "",
        "| Engine | Pages/s (all) | OCR pages | OCR pages/s | OCR ms/page p50 / p95 (in a worker) "
        "| Cold start | Peak worker RSS | Page errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, e in report.engines.items():
        lines.append(
            f"| {name} | {e.pipeline_pages_per_s:,.2f} | {e.ocr_pages} | "
            f"{_rate(e.ocr_pages_per_s, '')} | {e.ocr_ms_p50 or 'n/a'} / {e.ocr_ms_p95 or 'n/a'} | "
            f"{e.cold_start_s} s | {e.peak_worker_rss_mb or 'n/a'} MB | {e.page_errors} |"
        )
    lines += [
        "",
        "OCR pages/s divides the OCR pages by the wall time of the whole run (text-layer pages",
        "included), so it slightly understates OCR speed. Peak worker RSS is the largest",
        "resident set of any worker process so far in this run.",
    ]
    for name, e in report.engines.items():
        worst = sorted((p for p in e.pages if p.cer is not None), key=lambda p: -(p.cer or 0))[:8]
        lines += [
            "",
            f"## Worst pages: {name}",
            "",
            "| Page | Kind | Route | CER | WER |",
            "| --- | --- | --- | ---: | ---: |",
            *(
                f"| {p.doc_id} p{p.page} | {p.kind} | `{p.route}` | {fmt_pct(p.cer)} "
                f"| {fmt_pct(p.wer)} |"
                for p in worst
            ),
        ]
    lines.append("")
    return "\n".join(lines)


def write_parse_report(report: ParseEvalReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / "report.json", out_dir / "report.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_parse_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_parse_report(path: Path) -> ParseEvalReport:
    return ParseEvalReport.model_validate_json(path.read_text(encoding="utf-8"))


# ---- regression gate -------------------------------------------------------------------


@dataclass(frozen=True)
class ParseThresholds:
    max_routing_drop: float | None = 0.0
    max_digital_cer_increase: float | None = 0.001
    max_scanned_cer_increase: float | None = 0.01  # OCR output varies a little across CPUs
    max_field_recall_drop: float | None = 0.02
    min_speedup_vs_pypdf: float | None = 3.0  # same-job relative check, not a timing gate

    def checks(self, metrics: Sequence[str]) -> list[Check]:
        checks = []
        for metric in metrics:
            if metric.startswith("routing_"):
                checks.append(Check(metric, Direction.HIGHER_IS_BETTER, self.max_routing_drop))
            elif metric.endswith(".digital_cer"):
                checks.append(
                    Check(metric, Direction.LOWER_IS_BETTER, self.max_digital_cer_increase)
                )
            elif metric.endswith(".scanned_cer"):
                checks.append(
                    Check(metric, Direction.LOWER_IS_BETTER, self.max_scanned_cer_increase)
                )
            elif metric.endswith(".field_recall"):
                checks.append(Check(metric, Direction.HIGHER_IS_BETTER, self.max_field_recall_drop))
        return checks


@dataclass(frozen=True)
class ParseComparison(Comparison):
    speedup: float | None = None
    min_speedup: float | None = None

    @property
    def speedup_ok(self) -> bool:
        if self.min_speedup is None or self.speedup is None:
            return True
        return self.speedup >= self.min_speedup

    @property
    def passed(self) -> bool:
        return super().passed and self.speedup_ok


def compare_parse_reports(
    baseline: ParseEvalReport,
    candidate: ParseEvalReport,
    thresholds: ParseThresholds | None = None,
) -> ParseComparison:
    thresholds = thresholds or ParseThresholds()
    before, after = baseline.gate_metrics(), candidate.gate_metrics()
    results = []
    for check in thresholds.checks(list(before)):
        if check.metric not in after:  # engine missing in the candidate run
            results.append(CheckResult(check, before[check.metric], None, Status.REGRESSION))
            continue
        old, new = before[check.metric], after[check.metric]
        results.append(CheckResult(check, old, new, evaluate_check(check, old, new)))
    return ParseComparison(
        results=results,
        dataset_matches=baseline.meta.dataset_sha256 == candidate.meta.dataset_sha256,
        speedup=candidate.text_layer.speedup_vs_pypdf,
        min_speedup=thresholds.min_speedup_vs_pypdf,
    )


def render_parse_comparison(
    comparison: ParseComparison, baseline: ParseEvalReport, candidate: ParseEvalReport
) -> str:
    lines = [
        f"# Parse regression check: `{candidate.meta.run_name}` vs baseline "
        f"`{baseline.meta.run_name}`",
        "",
    ]
    if not comparison.dataset_matches:
        lines += ["> **Dataset mismatch**: the runs used different PDF sets.", ""]
    lines += [
        "| Metric | Baseline | Candidate | Delta | Tolerance | Status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in comparison.results:
        delta = "n/a" if r.delta is None else f"{r.delta * 100:+.2f} pp"
        tolerance = "off" if r.check.tolerance is None else f"{r.check.tolerance * 100:.1f} pp"
        lines.append(
            f"| `{r.check.metric}` | {fmt_pct(r.baseline)} | {fmt_pct(r.candidate)} | {delta} "
            f"| {tolerance} | {r.status.value} |"
        )
    if comparison.min_speedup is not None:
        status = "pass" if comparison.speedup_ok else "REGRESSION"
        if comparison.speedup is None:
            status = "skipped (pypdf not installed)"
        lines.append(
            f"| `text_layer_speedup_vs_pypdf` (same job) | - | "
            f"{comparison.speedup if comparison.speedup is not None else 'n/a'}x | - "
            f"| >= {comparison.min_speedup:.0f}x | {status} |"
        )
    lines += [
        "",
        "Throughput is reported, not gated: shared CI runners are too noisy for absolute timings.",
        "",
        f"**Result: {'PASS' if comparison.passed else 'FAIL'}**",
        "",
    ]
    return "\n".join(lines)
