"""Run the extractor over a labelled dataset and aggregate metrics into a report."""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from docextract import __version__
from docextract.evals.dataset import LabeledDocument
from docextract.evals.metrics import (
    Outcome,
    f1,
    match_line_items,
    percentile,
    safe_div,
    score_header_fields,
)
from docextract.extractor import Extractor
from docextract.prompts import PROMPT_VERSION
from docextract.schema import HEADER_FIELDS, ExtractionResult


class DocumentScore(BaseModel):
    id: str
    tags: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, Outcome]
    line_items_tp: int
    line_items_fp: int
    line_items_fn: int
    exact_match: bool
    schema_valid: bool
    first_attempt_schema_valid: bool
    used_fallback: bool
    attempts: int
    needs_review: bool
    expected_review: bool
    should_review: bool
    review_reasons: list[str]
    latency_ms: float
    cost_usd: float | None
    input_tokens: int
    output_tokens: int


class FieldStats(BaseModel):
    accuracy: float
    correct: int
    true_negative: int
    incorrect: int
    missed: int
    hallucinated: int


class Metrics(BaseModel):
    documents: int
    field_accuracy: float = Field(description="micro-average over all header fields")
    exact_match_rate: float
    schema_compliance_rate: float
    first_attempt_compliance_rate: float
    hallucination_rate: float | None
    line_items_precision: float | None
    line_items_recall: float | None
    line_items_f1: float | None
    review_flag_rate: float
    review_precision: float | None
    review_recall: float | None
    retry_rate: float
    fallback_rate: float
    mean_attempts: float
    total_cost_usd: float | None
    cost_per_doc_usd: float | None
    input_tokens: int
    output_tokens: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None


class SliceStats(BaseModel):
    documents: int
    field_accuracy: float
    exact_match_rate: float


class EvalMeta(BaseModel):
    run_name: str
    created_at: str
    package_version: str = __version__
    prompt_version: str = PROMPT_VERSION
    targets: list[str]
    dataset: str
    dataset_sha256: str


class EvalReport(BaseModel):
    meta: EvalMeta
    metrics: Metrics
    per_field: dict[str, FieldStats]
    slices: dict[str, dict[str, SliceStats]]
    documents: list[DocumentScore]


def score_document(doc: LabeledDocument, result: ExtractionResult) -> DocumentScore:
    predicted = result.document
    fields = score_header_fields(predicted, doc.label)
    tp, fp, fn = match_line_items(predicted.line_items if predicted else [], doc.label.line_items)
    exact = all(o.is_right for o in fields.values()) and fp == 0 and fn == 0
    return DocumentScore(
        id=doc.id,
        tags=doc.tags,
        fields=fields,
        line_items_tp=tp,
        line_items_fp=fp,
        line_items_fn=fn,
        exact_match=exact,
        schema_valid=result.schema_valid,
        first_attempt_schema_valid=result.first_attempt_schema_valid,
        used_fallback=result.used_fallback,
        attempts=result.attempts,
        needs_review=result.needs_review,
        expected_review=doc.expected_review,
        # A human should see it if the document itself is problematic OR we got it wrong.
        should_review=doc.expected_review or not exact,
        review_reasons=result.review_reasons,
        latency_ms=result.usage.latency_ms,
        cost_usd=result.usage.cost_usd,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )


def _field_stats(scores: Sequence[DocumentScore], name: str) -> FieldStats:
    counts = Counter(s.fields[name] for s in scores)
    right = counts[Outcome.CORRECT] + counts[Outcome.TRUE_NEGATIVE]
    return FieldStats(
        accuracy=right / len(scores),
        correct=counts[Outcome.CORRECT],
        true_negative=counts[Outcome.TRUE_NEGATIVE],
        incorrect=counts[Outcome.INCORRECT],
        missed=counts[Outcome.MISSED],
        hallucinated=counts[Outcome.HALLUCINATED],
    )


def _micro_accuracy(scores: Sequence[DocumentScore]) -> float:
    outcomes = [o for s in scores for o in s.fields.values()]
    return sum(o.is_right for o in outcomes) / len(outcomes)


def aggregate(scores: Sequence[DocumentScore]) -> Metrics:
    if not scores:
        raise ValueError("cannot aggregate an empty evaluation")
    n = len(scores)
    outcomes = Counter(o for s in scores for o in s.fields.values())
    tp = sum(s.line_items_tp for s in scores)
    fp = sum(s.line_items_fp for s in scores)
    fn = sum(s.line_items_fn for s in scores)
    li_precision, li_recall = safe_div(tp, tp + fp), safe_div(tp, tp + fn)
    flagged = [s for s in scores if s.needs_review]
    should = [s for s in scores if s.should_review]
    costs = [s.cost_usd for s in scores]
    total_cost = None if any(c is None for c in costs) else sum(costs)
    latencies = [s.latency_ms for s in scores]
    return Metrics(
        documents=n,
        field_accuracy=_micro_accuracy(scores),
        exact_match_rate=sum(s.exact_match for s in scores) / n,
        schema_compliance_rate=sum(s.schema_valid for s in scores) / n,
        first_attempt_compliance_rate=sum(s.first_attempt_schema_valid for s in scores) / n,
        hallucination_rate=safe_div(
            outcomes[Outcome.HALLUCINATED],
            outcomes[Outcome.HALLUCINATED] + outcomes[Outcome.TRUE_NEGATIVE],
        ),
        line_items_precision=li_precision,
        line_items_recall=li_recall,
        line_items_f1=f1(li_precision, li_recall),
        review_flag_rate=len(flagged) / n,
        review_precision=safe_div(sum(s.should_review for s in flagged), len(flagged)),
        review_recall=safe_div(sum(s.needs_review for s in should), len(should)),
        retry_rate=sum(s.attempts > 1 for s in scores) / n,
        fallback_rate=sum(s.used_fallback for s in scores) / n,
        mean_attempts=sum(s.attempts for s in scores) / n,
        total_cost_usd=total_cost,
        cost_per_doc_usd=None if total_cost is None else total_cost / n,
        input_tokens=sum(s.input_tokens for s in scores),
        output_tokens=sum(s.output_tokens for s in scores),
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
    )


def _slices(scores: Sequence[DocumentScore]) -> dict[str, dict[str, SliceStats]]:
    grouped: dict[str, dict[str, list[DocumentScore]]] = defaultdict(lambda: defaultdict(list))
    for score in scores:
        for key, value in score.tags.items():
            grouped[key][value].append(score)
    return {
        key: {
            value: SliceStats(
                documents=len(group),
                field_accuracy=_micro_accuracy(group),
                exact_match_rate=sum(s.exact_match for s in group) / len(group),
            )
            for value, group in sorted(groups.items())
        }
        for key, groups in sorted(grouped.items())
    }


def run_eval(
    extractor: Extractor,
    documents: Sequence[LabeledDocument],
    *,
    run_name: str,
    dataset: str,
    dataset_sha256: str,
    workers: int = 1,
    on_result: Callable[[LabeledDocument, ExtractionResult], None] | None = None,
) -> EvalReport:
    def work(doc: LabeledDocument) -> DocumentScore:
        result = extractor.extract(doc.text)
        if on_result:
            on_result(doc, result)
        return score_document(doc, result)

    scores: Iterable[DocumentScore]
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            scores = list(pool.map(work, documents))
    else:
        scores = [work(doc) for doc in documents]
    scores = list(scores)

    return EvalReport(
        meta=EvalMeta(
            run_name=run_name,
            created_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            targets=[t.label for t in extractor.targets],
            dataset=dataset,
            dataset_sha256=dataset_sha256,
        ),
        metrics=aggregate(scores),
        per_field={name: _field_stats(scores, name) for name in HEADER_FIELDS},
        slices=_slices(scores),
        documents=scores,
    )
