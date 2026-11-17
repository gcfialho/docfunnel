"""Run the parse-stage eval: every OCR engine through the page pool, then score."""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from pathlib import Path

from docfunnel.datasets.pdfs import load_manifest, manifest_sha256
from docfunnel.evals.parse.bench import bench_text_layer
from docfunnel.evals.parse.environment import hardware_info, package_versions, peak_child_rss_mb
from docfunnel.evals.parse.models import (
    EngineResult,
    PageRecord,
    ParseEvalMeta,
    ParseEvalReport,
    RoutingMetrics,
)
from docfunnel.evals.parse.scoring import score_engine, score_routing
from docfunnel.evals.stats import percentile
from docfunnel.parse.ocr import resolve_engine_name
from docfunnel.parse.pipeline import (
    PagePool,
    ParseOptions,
    default_workers,
)


@dataclass
class ParseEvalConfig:
    dataset: Path
    engines: list[str] = field(default_factory=lambda: ["auto"])
    workers: int | None = None
    ocr_threads: int = 1  # ONNX Runtime threads per worker
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
        options = ParseOptions(ocr_engine=name, dpi=config.dpi, ocr_threads=config.ocr_threads)
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
            peak_worker_rss_mb=peak_child_rss_mb(),
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
        ocr_threads=config.ocr_threads,
        dpi=config.dpi,
        versions=package_versions(),
        hardware=hardware_info(),
    )
    return ParseEvalReport(
        meta=meta, routing=routing, misrouted=misrouted, text_layer=text_layer, engines=results
    )
