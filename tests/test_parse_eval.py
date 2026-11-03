"""Parse-stage eval: scoring, report round trip, regression gate and CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("reportlab")
pytest.importorskip("pypdfium2")

from docfunnel.cli import app
from docfunnel.evals.metrics import char_error_rate, quote_found, word_error_rate
from docfunnel.evals.parse_eval import (
    ParseEvalConfig,
    ParseEvalReport,
    ParseThresholds,
    compare_parse_reports,
    load_parse_report,
    render_parse_comparison,
    render_parse_markdown,
    run_parse_eval,
    write_parse_report,
)
from docfunnel.synthetic_pdf import write_pdf_dataset

runner = CliRunner()


def test_text_metrics() -> None:
    assert char_error_rate("Total  due\n12,00", "Total due 12,00") == 0.0
    assert char_error_rate("abcd", "abed") == pytest.approx(0.25)
    assert word_error_rate("total due now", "total dve now") == pytest.approx(1 / 3)
    assert char_error_rate("", "") == 0.0
    assert char_error_rate("", "x") == 1.0
    assert quote_found("R$ 1.234,50", "Total R$1.234,50 due")
    assert not quote_found("1.234,50", "1.284,50")


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("pdfs")
    write_pdf_dataset(out, n=6, seed=11)
    return out


@pytest.fixture(scope="module")
def report(dataset: Path) -> ParseEvalReport:
    config = ParseEvalConfig(dataset=dataset, engines=["none"], workers=2, bench_repeats=1)
    return run_parse_eval(config)


def test_report_scores_routing_text_and_fields(report: ParseEvalReport) -> None:
    routing = report.routing
    assert routing.pages == report.meta.pages
    assert routing.true_positive + routing.false_negative == sum(report.meta.scanned_pages.values())
    assert routing.recall == 1.0  # every image-only page is sent to OCR
    result = report.engines["none"]
    assert result.quality["digital"].cer == 0.0
    assert result.field_recall["digital"].recall == 1.0
    # Without an OCR engine, scanned pages have (almost) no text.
    assert result.quality["scanned"].cer > 0.9
    assert result.page_errors == 0
    assert report.text_layer.pages == result.quality["digital"].pages
    assert report.text_layer.pypdfium2_pages_per_s > 0
    assert report.meta.hardware.logical_cores >= 1
    assert "pypdfium2" in report.meta.versions


def test_report_round_trip_and_markdown(report: ParseEvalReport, tmp_path: Path) -> None:
    json_path, md_path = write_parse_report(report, tmp_path)
    assert load_parse_report(json_path) == report
    markdown = md_path.read_text()
    for heading in ("## OCR routing", "## Text quality", "## Field recall", "## Throughput"):
        assert heading in markdown
    assert report.meta.hardware.cpu in render_parse_markdown(report)


def test_compare_passes_on_identical_runs_and_catches_regressions(
    report: ParseEvalReport,
) -> None:
    thresholds = ParseThresholds(min_speedup_vs_pypdf=None)
    assert compare_parse_reports(report, report, thresholds).passed

    worse = report.model_copy(deep=True)
    worse.routing.recall = 0.5
    worse.engines["none"].field_recall["all"].recall = 0.1
    comparison = compare_parse_reports(report, worse, thresholds)
    assert not comparison.passed
    failed = {r.check.metric for r in comparison.results if r.status.value == "REGRESSION"}
    assert failed == {"routing_recall", "none.field_recall"}
    assert "FAIL" in render_parse_comparison(comparison, report, worse)


def test_speedup_check_and_dataset_mismatch(report: ParseEvalReport) -> None:
    slow = report.model_copy(deep=True)
    slow.text_layer.speedup_vs_pypdf = 1.5
    assert not compare_parse_reports(report, slow, ParseThresholds(min_speedup_vs_pypdf=3)).passed
    other = report.model_copy(deep=True)
    other.meta.dataset_sha256 = "different"
    assert not compare_parse_reports(
        report, other, ParseThresholds(min_speedup_vs_pypdf=None)
    ).passed


def test_cli_eval_parse_then_compare(dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "eval-parse",
            "--data",
            str(dataset),
            "--out",
            str(out),
            "--ocr-engine",
            "none",
            "--workers",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "OCR routing accuracy" in result.output
    report_path = out / "report.json"
    compared = runner.invoke(
        app,
        [
            "compare-parse",
            str(report_path),
            str(report_path),
            "--min-speedup-vs-pypdf",
            "0",
            "--out",
            str(tmp_path / "cmp.md"),
        ],
    )
    assert compared.exit_code == 0, compared.output
    assert "PASS" in (tmp_path / "cmp.md").read_text()


def test_cli_eval_parse_requires_a_dataset(tmp_path: Path) -> None:
    result = runner.invoke(app, ["eval-parse", "--data", str(tmp_path)])
    assert result.exit_code == 2
    assert "generate-pdfs" in result.output
