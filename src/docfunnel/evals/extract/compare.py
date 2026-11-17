"""Regression check between two evaluation runs (baseline vs candidate).

Designed for CI: ``docfunnel compare baseline.json candidate.json`` exits non-zero
when a quality metric drops (or a cost/latency metric grows) beyond its threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from docfunnel.evals.extract.runner import EvalReport
from docfunnel.evals.formatting import fmt_ms, fmt_pct, fmt_usd
from docfunnel.evals.gate import (
    Check,
    CheckResult,
    Comparison,
    Direction,
    evaluate_check,
)


@dataclass(frozen=True)
class Thresholds:
    max_accuracy_drop: float | None = 0.01
    max_exact_match_drop: float | None = 0.02
    max_schema_compliance_drop: float | None = 0.0
    max_hallucination_increase: float | None = 0.01
    max_review_recall_drop: float | None = 0.05
    max_cost_increase: float | None = 0.20  # relative
    max_p95_latency_increase: float | None = None  # relative; off by default (noisy in CI)

    def checks(self) -> list[Check]:
        return [
            Check("field_accuracy", Direction.HIGHER_IS_BETTER, self.max_accuracy_drop),
            Check("exact_match_rate", Direction.HIGHER_IS_BETTER, self.max_exact_match_drop),
            Check(
                "schema_compliance_rate",
                Direction.HIGHER_IS_BETTER,
                self.max_schema_compliance_drop,
            ),
            Check("hallucination_rate", Direction.LOWER_IS_BETTER, self.max_hallucination_increase),
            Check("review_recall", Direction.HIGHER_IS_BETTER, self.max_review_recall_drop),
            Check(
                "cost_per_doc_usd", Direction.LOWER_IS_BETTER, self.max_cost_increase, relative=True
            ),
            Check(
                "latency_p95_ms",
                Direction.LOWER_IS_BETTER,
                self.max_p95_latency_increase,
                relative=True,
            ),
        ]


def compare_reports(
    baseline: EvalReport, candidate: EvalReport, thresholds: Thresholds | None = None
) -> Comparison:
    thresholds = thresholds or Thresholds()
    results = []
    for check in thresholds.checks():
        before = getattr(baseline.metrics, check.metric)
        after = getattr(candidate.metrics, check.metric)
        results.append(CheckResult(check, before, after, evaluate_check(check, before, after)))
    return Comparison(
        results=results,
        dataset_matches=baseline.meta.dataset_sha256 == candidate.meta.dataset_sha256,
    )


def _fmt(metric: str, value: float | None) -> str:
    if metric.endswith("_usd"):
        return fmt_usd(value)
    if metric.endswith("_ms"):
        return fmt_ms(value)
    return fmt_pct(value)


def render_comparison(comparison: Comparison, baseline: EvalReport, candidate: EvalReport) -> str:
    lines = [
        f"# Regression check: `{candidate.meta.run_name}` vs baseline `{baseline.meta.run_name}`",
        "",
    ]
    if not comparison.dataset_matches:
        lines += [
            "> **Dataset mismatch**: the runs used different datasets; metrics are not comparable.",
            "",
        ]
    lines += [
        "| Metric | Baseline | Candidate | Delta | Tolerance | Status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in comparison.results:
        metric = r.check.metric
        if r.delta is None:
            delta = "n/a"
        elif metric.endswith(("_usd", "_ms")):
            delta = f"{r.delta:+.6g}"
        else:
            delta = f"{r.delta * 100:+.1f} pp"
        if r.check.tolerance is None:
            tolerance = "off"
        elif r.check.relative:
            tolerance = f"{r.check.tolerance * 100:.0f}% rel"
        else:
            tolerance = f"{r.check.tolerance * 100:.1f} pp"
        lines.append(
            f"| `{metric}` | {_fmt(metric, r.baseline)} | {_fmt(metric, r.candidate)} "
            f"| {delta} | {tolerance} | {r.status.value} |"
        )
    lines += ["", f"**Result: {'PASS' if comparison.passed else 'FAIL'}**", ""]
    return "\n".join(lines)
