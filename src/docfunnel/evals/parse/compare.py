"""Regression gate for the parse stage (``docfunnel compare-parse``)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from docfunnel.evals.formatting import fmt_pct
from docfunnel.evals.gate import (
    Check,
    CheckResult,
    Comparison,
    Direction,
    Status,
    evaluate_check,
)
from docfunnel.evals.parse.models import (
    ParseEvalReport,
)


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
        if check.metric not in after:  # engine not run in the candidate (e.g. no Tesseract in CI)
            results.append(CheckResult(check, before[check.metric], None, Status.SKIPPED))
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
