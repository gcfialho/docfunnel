"""Write evaluation reports as JSON (machine-readable) and Markdown (human-readable)."""

from __future__ import annotations

from pathlib import Path

from docextract.evals.runner import EvalReport


def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def fmt_usd(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.6f}"


def fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f} ms"


def summary_rows(report: EvalReport) -> list[tuple[str, str]]:
    m = report.metrics
    return [
        ("Documents", str(m.documents)),
        ("Field accuracy (micro, 9 header fields)", fmt_pct(m.field_accuracy)),
        ("Document exact match", fmt_pct(m.exact_match_rate)),
        ("Schema compliance (final)", fmt_pct(m.schema_compliance_rate)),
        ("Schema compliance (first attempt)", fmt_pct(m.first_attempt_compliance_rate)),
        ("Hallucination rate (null fields filled)", fmt_pct(m.hallucination_rate)),
        ("Line items F1", fmt_pct(m.line_items_f1)),
        ("Review flag rate", fmt_pct(m.review_flag_rate)),
        (
            "Review precision / recall",
            f"{fmt_pct(m.review_precision)} / {fmt_pct(m.review_recall)}",
        ),
        (
            "Docs needing a retry / fallback",
            f"{fmt_pct(m.retry_rate)} / {fmt_pct(m.fallback_rate)}",
        ),
        ("Tokens (input / output)", f"{m.input_tokens:,} / {m.output_tokens:,}"),
        ("Total cost / per doc", f"{fmt_usd(m.total_cost_usd)} / {fmt_usd(m.cost_per_doc_usd)}"),
        ("Latency p50 / p95", f"{fmt_ms(m.latency_p50_ms)} / {fmt_ms(m.latency_p95_ms)}"),
    ]


def render_markdown(report: EvalReport) -> str:
    meta = report.meta
    lines = [
        f"# Evaluation report: {meta.run_name}",
        "",
        f"- Targets: {', '.join(f'`{t}`' for t in meta.targets)}",
        f"- Dataset: `{meta.dataset}` (sha256 `{meta.dataset_sha256[:12]}`)",
        f"- Prompt version: `{meta.prompt_version}` - package `{meta.package_version}`",
        f"- Created: {meta.created_at}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        *(f"| {name} | {value} |" for name, value in summary_rows(report)),
        "",
        "## Per-field results",
        "",
        "| Field | Accuracy | Correct | True null | Incorrect | Missed | Hallucinated |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, s in report.per_field.items():
        lines.append(
            f"| `{name}` | {fmt_pct(s.accuracy)} | {s.correct} | {s.true_negative} | "
            f"{s.incorrect} | {s.missed} | {s.hallucinated} |"
        )
    for key, groups in report.slices.items():
        lines += [
            "",
            f"## By {key}",
            "",
            "| Value | Docs | Field accuracy | Exact match |",
            "| --- | ---: | ---: | ---: |",
        ]
        for value, stats in groups.items():
            lines.append(
                f"| {value} | {stats.documents} | {fmt_pct(stats.field_accuracy)} | "
                f"{fmt_pct(stats.exact_match_rate)} |"
            )

    failures = [d for d in report.documents if not d.exact_match or not d.schema_valid]
    lines += ["", "## Documents with errors", ""]
    if not failures:
        lines.append("None.")
    else:
        lines += [
            "| Document | Wrong fields | Line items (fp/fn) | Flagged for review | Reasons |",
            "| --- | --- | --- | --- | --- |",
        ]
        for d in failures:
            wrong = ", ".join(f"{k} ({v.value})" for k, v in d.fields.items() if not v.is_right)
            reasons = ", ".join(d.review_reasons) or "-"
            lines.append(
                f"| {d.id} | {wrong or '-'} | {d.line_items_fp}/{d.line_items_fn} | "
                f"{'yes' if d.needs_review else '**no**'} | {reasons} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_report(report: EvalReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_report(path: Path) -> EvalReport:
    return EvalReport.model_validate_json(path.read_text(encoding="utf-8"))
