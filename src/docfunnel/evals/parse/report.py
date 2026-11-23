"""Render a parse eval report as Markdown and read/write ``report.{json,md}``."""

from __future__ import annotations

from pathlib import Path

from docfunnel.evals.formatting import fmt_pct
from docfunnel.evals.parse.models import (
    ParseEvalReport,
)


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
        f"- Page pool: {meta.workers} worker processes x {meta.ocr_threads} OCR thread(s); "
        f"OCR render at {meta.dpi} dpi",
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
        f"Full pipeline in the page pool ({meta.workers} processes x "
        f"{meta.ocr_threads} thread(s)):",
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
