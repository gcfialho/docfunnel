"""Report schema of the parse-stage eval (``report.json``)."""

from __future__ import annotations

from pydantic import BaseModel

from docfunnel import __version__


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
    ocr_threads: int
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
