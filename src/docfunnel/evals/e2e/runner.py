"""Run the end-to-end comparison: the docfunnel route against native PDF input.

For every model and every document:

* **docfunnel**: the parse stage reads the PDF on the CPU (text layer, OCR only on the
  pages that need it), and the model gets the text. The parse runs once per document
  and its CPU time is reported next to the model's latency.
* **native**: the PDF itself goes to the model as a file, the way an application
  without a parse stage would send it.
* **hybrid**: the text of the pages the parse stage read from the text layer, plus an
  image of each page it routed to OCR, so the model reads the scans itself. On a
  document with no scanned page it is the docfunnel route; that result is reused
  rather than paid for twice.

All routes use the same prompt, output schema, repair turn and scoring
(:func:`docfunnel.evals.extract.runner.score_document`). Spending is capped per
provider: once a provider's recorded cost reaches its budget, its remaining calls are
skipped and reported as such, never run.
"""

from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from docfunnel import __version__
from docfunnel.config import Settings, build_extractor
from docfunnel.evals.e2e.dataset import E2EDoc, load_e2e_set
from docfunnel.evals.extract.dataset import LabeledDocument
from docfunnel.evals.extract.runner import DocumentScore, Metrics, aggregate, score_document
from docfunnel.extract.extractor import Extractor
from docfunnel.extract.prompts import PROMPT_VERSION
from docfunnel.parse.model import ParsedDocument
from docfunnel.parse.pipeline import PagePool, ParseOptions
from docfunnel.providers.base import Attachment

ROUTES = ("docfunnel", "native", "hybrid")
DEFAULT_ROUTES = ("docfunnel", "native")


class E2ERow(BaseModel):
    doc_id: str
    model: str
    route: str
    skipped: bool = False
    score: DocumentScore | None = None
    parse_cpu_ms: float = 0.0
    reused: bool = False
    """Hybrid route on a document without scanned pages: the docfunnel result, not a call."""


class E2EGroup(BaseModel):
    model: str
    route: str
    slice: str  # "all", "size=small", "scan=digital", ...
    metrics: Metrics


class E2EMeta(BaseModel):
    run_name: str
    created_at: str
    package_version: str
    prompt_version: str
    dataset: str
    documents: int
    pages: int
    targets: list[str]
    routes: list[str]
    budget_usd: dict[str, float]
    spent_usd: dict[str, float]
    skipped_calls: int


class E2EReport(BaseModel):
    meta: E2EMeta
    groups: list[E2EGroup]
    rows: list[E2ERow]


@dataclass
class E2EConfig:
    dataset: Path
    targets: list[tuple[str, str]]
    routes: tuple[str, ...] = DEFAULT_ROUTES
    budget_usd: dict[str, float] = field(default_factory=dict)
    default_budget_usd: float = 4.0
    max_attempts: int = 2
    compact_output: bool = False
    max_output_tokens: int = 16_384  # a 170-line invoice is ~6k tokens of JSON, plus thinking
    workers: int = 4
    limit: int | None = None
    parse_options: ParseOptions = field(default_factory=lambda: ParseOptions(ocr_engine="auto"))
    run_name: str | None = None
    hybrid_dpi: int = 150
    where: dict[str, str] = field(default_factory=dict)
    """Only documents whose tags match, e.g. ``{"scan": "has_scanned_pages"}``."""


class _Budget:
    """Recorded spend per provider, checked before every document."""

    def __init__(self, limits: dict[str, float], default: float) -> None:
        self._limits, self._default = limits, default
        self.spent: dict[str, float] = {}
        self._lock = threading.Lock()

    def limit(self, provider: str) -> float:
        return self._limits.get(provider, self._default)

    def allows(self, provider: str) -> bool:
        with self._lock:
            return self.spent.get(provider, 0.0) < self.limit(provider)

    def add(self, provider: str, cost: float | None) -> None:
        with self._lock:
            self.spent[provider] = self.spent.get(provider, 0.0) + (cost or 0.0)


def _parse_all(
    docs: Sequence[E2EDoc], directory: Path, options: ParseOptions
) -> dict[str, ParsedDocument]:
    """The parse stage, once per document."""
    with PagePool(options) as pool:
        parsed = pool.parse([directory / d.file for d in docs], [d.id for d in docs])
    return {doc.doc_id: doc for doc in parsed}


def _cpu_ms(document: ParsedDocument) -> float:
    return sum(page.timings_ms.get("total", 0.0) for page in document.pages)


def _page_jpeg(path: Path, index: int, dpi: int) -> bytes:
    import io

    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        image = pdf[index].render(scale=dpi / 72, grayscale=True).to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()
    finally:
        pdf.close()


def hybrid_inputs(document: ParsedDocument, pdf: Path, dpi: int) -> tuple[str, list[Attachment]]:
    """Text of the text-layer pages, and a JPEG of each page the parse stage sent to OCR."""
    parts: list[str] = []
    images: list[Attachment] = []
    for page in document.pages:
        if page.source == "ocr":
            images.append(Attachment(_page_jpeg(pdf, page.number - 1, dpi), "image/jpeg"))
            note = f"[Page {page.number} is a scan: read it from attached image {len(images)}.]"
            parts.append(note)
        else:
            parts.append(page.text)
    return "\n\n".join(parts), images


def run_e2e(
    config: E2EConfig,
    *,
    make_extractor: Callable[[str, str, E2EConfig], Extractor] | None = None,
    on_row: Callable[[E2ERow], None] | None = None,
) -> E2EReport:
    docs = [
        d
        for d in load_e2e_set(config.dataset)
        if all(d.tags.get(k) == v for k, v in config.where.items())
    ][: config.limit]
    routes = sorted(config.routes, key=ROUTES.index)  # docfunnel before hybrid, for reuse
    parsed: dict[str, ParsedDocument] = {}
    if {"docfunnel", "hybrid"} & set(routes):
        parsed = _parse_all(docs, config.dataset, config.parse_options)
    text_scores: dict[tuple[str, str], DocumentScore] = {}
    # PDFium is not thread-safe: render the hybrid route's page images here, once per
    # document and in this thread, before the model calls run in the worker threads.
    hybrid: dict[str, tuple[str, list[Attachment]]] = {}
    if "hybrid" in routes:
        hybrid = {
            d.id: hybrid_inputs(parsed[d.id], config.dataset / d.file, config.hybrid_dpi)
            for d in docs
        }
    budget = _Budget(config.budget_usd, config.default_budget_usd)
    factory = make_extractor or _default_extractor
    rows: list[E2ERow] = []
    lock = threading.Lock()

    def run_one(extractor: Extractor, provider: str, model: str, route: str, doc: E2EDoc) -> None:
        row = E2ERow(doc_id=doc.id, model=model, route=route)
        if not budget.allows(provider):
            row.skipped = True
        else:
            labeled = LabeledDocument(id=doc.id, text="", label=doc.label, tags=doc.tags)
            pdf = config.dataset / doc.file
            result = None
            if route == "docfunnel":
                row.parse_cpu_ms = _cpu_ms(parsed[doc.id])
                result = extractor.extract(parsed[doc.id].text)
            elif route == "native":
                data = pdf.read_bytes()
                result = extractor.extract(attachments=[Attachment(data, "application/pdf")])
            else:
                row.parse_cpu_ms = _cpu_ms(parsed[doc.id])
                text, images = hybrid[doc.id]
                if not images and (model, doc.id) in text_scores:
                    row.score, row.reused = text_scores[(model, doc.id)], True
                else:
                    result = extractor.extract(text, attachments=images)
            if result is not None:
                budget.add(provider, result.usage.cost_usd)
                row.score = score_document(labeled, result)
                if route == "docfunnel":
                    with lock:
                        text_scores[(model, doc.id)] = row.score
        with lock:
            rows.append(row)
        if on_row is not None:
            on_row(row)

    for provider, model in config.targets:
        extractor = factory(provider, model, config)
        for route in routes:
            with ThreadPoolExecutor(max_workers=config.workers) as pool:
                for future in [
                    pool.submit(run_one, extractor, provider, model, route, doc) for doc in docs
                ]:
                    future.result()

    order = {(p, m): i for i, (p, m) in enumerate(config.targets)}
    model_rank = {m: order[(p, m)] for p, m in config.targets}
    rows.sort(key=lambda r: (model_rank[r.model], ROUTES.index(r.route), r.doc_id))
    meta = E2EMeta(
        run_name=config.run_name or f"e2e ({len(config.targets)} models)",
        created_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        package_version=__version__,
        prompt_version=PROMPT_VERSION + ("-compact" if config.compact_output else ""),
        dataset=config.dataset.as_posix(),
        documents=len(docs),
        pages=sum(d.pages for d in docs),
        targets=[f"{p}:{m}" for p, m in config.targets],
        routes=routes,
        budget_usd={p: budget.limit(p) for p, _ in config.targets},
        spent_usd={p: round(v, 6) for p, v in budget.spent.items()},
        skipped_calls=sum(r.skipped for r in rows),
    )
    return E2EReport(meta=meta, groups=_groups(rows, docs), rows=rows)


def _default_extractor(provider: str, model: str, config: E2EConfig) -> Extractor:
    settings = Settings(
        provider=provider,
        model=model,
        max_attempts=config.max_attempts,
        max_output_tokens=config.max_output_tokens,
        compact_output=config.compact_output,
    )
    return build_extractor(settings)


def _groups(rows: Sequence[E2ERow], docs: Sequence[E2EDoc]) -> list[E2EGroup]:
    tags = {d.id: d.tags for d in docs}
    groups: list[E2EGroup] = []
    keys = list(dict.fromkeys((r.model, r.route) for r in rows))
    for model, route in keys:
        scored = [r for r in rows if r.model == model and r.route == route and r.score]
        slices: dict[str, list[DocumentScore]] = {"all": []}
        for row in scored:
            assert row.score is not None
            slices["all"].append(row.score)
            for key, value in tags[row.doc_id].items():
                slices.setdefault(f"{key}={value}", []).append(row.score)
        for name, scores in slices.items():
            if scores:
                groups.append(
                    E2EGroup(model=model, route=route, slice=name, metrics=aggregate(scores))
                )
    return groups


def parse_cpu_ms(report: E2EReport, model: str, route: str, slice_: str = "all") -> float | None:
    """Mean parse CPU time per document for a group (docfunnel route only)."""
    if route != "docfunnel":
        return None
    docs = _slice_docs(report, slice_)
    values = [
        r.parse_cpu_ms
        for r in report.rows
        if r.model == model and r.route == route and r.score and r.doc_id in docs
    ]
    return sum(values) / len(values) if values else None


def _slice_docs(report: E2EReport, slice_: str) -> set[str]:
    ids = {r.doc_id for r in report.rows}
    if slice_ == "all":
        return ids
    key, _, value = slice_.partition("=")
    return {r.doc_id for r in report.rows if r.score and r.score.tags.get(key) == value}
