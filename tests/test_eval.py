"""Integration tests: the full eval harness through the offline fake provider."""

import json
from pathlib import Path

import pytest

from docfunnel.config import Settings, build_extractor
from docfunnel.evals.compare import Status, Thresholds, compare_reports, render_comparison
from docfunnel.evals.dataset import file_sha256, load_dataset
from docfunnel.evals.report import load_report, render_markdown, write_report
from docfunnel.evals.runner import EvalReport, run_eval

from helpers import DATASET

pytestmark = pytest.mark.integration


def run(
    fallbacks: tuple[tuple[str, str], ...] = (("fake", "fake-pro"),),
    model: str = "fake-mini",
    limit: int | None = None,
) -> EvalReport:
    extractor = build_extractor(Settings(provider="fake", model=model, fallbacks=fallbacks))
    return run_eval(
        extractor,
        load_dataset(DATASET, limit=limit),
        run_name=model,
        dataset=str(DATASET),
        dataset_sha256=file_sha256(DATASET),
    )


@pytest.fixture(scope="module")
def report() -> EvalReport:
    return run()


def test_metrics_are_well_formed(report: EvalReport) -> None:
    m = report.metrics
    assert m.documents == 60
    for value in (
        m.field_accuracy,
        m.exact_match_rate,
        m.schema_compliance_rate,
        m.first_attempt_compliance_rate,
        m.review_flag_rate,
    ):
        assert 0.0 <= value <= 1.0
    assert m.first_attempt_compliance_rate < m.schema_compliance_rate  # repair helps
    assert m.retry_rate > 0
    assert m.fallback_rate > 0
    assert m.total_cost_usd == 0.0  # fake models are priced at zero
    assert m.input_tokens > 0
    assert m.latency_p50_ms is not None
    assert m.latency_p95_ms is not None
    assert m.latency_p50_ms <= m.latency_p95_ms


def test_fallback_raises_schema_compliance() -> None:
    without = run(fallbacks=())
    assert without.metrics.schema_compliance_rate < 1.0
    assert without.metrics.fallback_rate == 0.0
    assert run().metrics.schema_compliance_rate == 1.0


def test_eval_is_deterministic_apart_from_latency(report: EvalReport) -> None:
    again = run()
    strip = {"latency_p50_ms", "latency_p95_ms"}
    assert again.metrics.model_dump(exclude=strip) == report.metrics.model_dump(exclude=strip)


def test_per_field_and_slices(report: EvalReport) -> None:
    assert set(report.per_field) >= {"vendor_name", "date", "total"}
    assert set(report.slices) == {"layout", "locale", "variant"}
    clean = report.slices["variant"]["clean"]
    noisy = report.slices["variant"]["ocr_noise"]
    assert clean.field_accuracy >= noisy.field_accuracy


def test_misprinted_documents_are_flagged(report: EvalReport) -> None:
    misprinted = [d for d in report.documents if d.tags["variant"] == "misprinted"]
    assert misprinted
    assert all(d.needs_review for d in misprinted)


def test_report_round_trip(tmp_path: Path, report: EvalReport) -> None:
    json_path, md_path = write_report(report, tmp_path)
    assert load_report(json_path) == report
    markdown = md_path.read_text()
    assert "| Field accuracy" in markdown
    assert "## By variant" in markdown
    assert json.loads(json_path.read_text())["metrics"]["documents"] == 60
    assert render_markdown(report) == markdown


def test_compare_identical_runs_pass(report: EvalReport) -> None:
    comparison = compare_reports(report, report)
    assert comparison.passed
    statuses = {r.check.metric: r.status for r in comparison.results}
    assert statuses["latency_p95_ms"] is Status.SKIPPED  # off by default


def test_compare_detects_regression(report: EvalReport) -> None:
    worse = run(fallbacks=())  # no fallback -> lower schema compliance
    comparison = compare_reports(report, worse)
    assert not comparison.passed
    failed = {r.check.metric for r in comparison.results if r.status is Status.REGRESSION}
    assert "schema_compliance_rate" in failed
    assert "REGRESSION" in render_comparison(comparison, report, worse)


def test_compare_thresholds_can_be_relaxed(report: EvalReport) -> None:
    worse = run(fallbacks=())
    lenient = Thresholds(
        max_accuracy_drop=1,
        max_exact_match_drop=1,
        max_schema_compliance_drop=1,
        max_hallucination_increase=1,
        max_review_recall_drop=1,
    )
    assert compare_reports(report, worse, lenient).passed


def test_compare_rejects_different_datasets(report: EvalReport) -> None:
    other = report.model_copy(
        update={"meta": report.meta.model_copy(update={"dataset_sha256": "different"})}
    )
    comparison = compare_reports(report, other)
    assert not comparison.dataset_matches
    assert not comparison.passed


def test_relative_cost_threshold(report: EvalReport) -> None:
    def with_cost(cost: float) -> EvalReport:
        return report.model_copy(
            update={"metrics": report.metrics.model_copy(update={"cost_per_doc_usd": cost})}
        )

    thresholds = Thresholds(max_cost_increase=0.2)
    assert compare_reports(with_cost(1.0), with_cost(1.19), thresholds).passed
    assert not compare_reports(with_cost(1.0), with_cost(1.21), thresholds).passed
