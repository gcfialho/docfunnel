"""Render an end-to-end report as Markdown and read/write ``report.{json,md}``."""

from __future__ import annotations

from pathlib import Path

from docfunnel.evals.e2e.runner import E2EGroup, E2EReport, parse_cpu_ms
from docfunnel.evals.formatting import fmt_pct


def _usd(value: float | None, digits: int = 4) -> str:
    return "unknown" if value is None else f"${value:.{digits}f}"


def _per_doc(total: int, docs: int) -> str:
    return f"{total / docs:,.0f}" if docs else "n/a"


def _seconds(ms: float | None) -> str:
    return "n/a" if ms is None else f"{ms / 1000:.1f} s"


def _group_row(report: E2EReport, group: E2EGroup) -> str:
    m = group.metrics
    per_1k = None if m.cost_per_doc_usd is None else m.cost_per_doc_usd * 1000
    parse = parse_cpu_ms(report, group.model, group.route, group.slice)
    return (
        f"| `{group.model}` | {group.route} | {m.documents} | {fmt_pct(m.field_accuracy)} "
        f"| {fmt_pct(m.exact_match_rate)} | {fmt_pct(m.line_items_f1)} "
        f"| {fmt_pct(m.schema_compliance_rate)} | {_per_doc(m.input_tokens, m.documents)} "
        f"| {_per_doc(m.output_tokens, m.documents)} | {_usd(m.cost_per_doc_usd, 5)} "
        f"| {_usd(per_1k, 2)} | {_seconds(m.latency_p50_ms)} | {_seconds(parse)} |"
    )


_HEADER = [
    "| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid "
    "| Input tok/doc | Output tok/doc | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |",
    "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
]


def _comparison(report: E2EReport, slice_: str) -> list[str]:
    """Native against docfunnel, per model: what the parse stage saves or costs."""
    lines = [
        "| Model | Input tokens (native / docfunnel) | Cost (native / docfunnel) "
        "| Field accuracy (docfunnel - native) | Exact match (docfunnel - native) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    by_key = {(g.model, g.route): g.metrics for g in report.groups if g.slice == slice_}
    for model in dict.fromkeys(g.model for g in report.groups):
        native, ours = by_key.get((model, "native")), by_key.get((model, "docfunnel"))
        if native is None or ours is None:
            continue
        tokens = native.input_tokens / ours.input_tokens if ours.input_tokens else None
        cost = (
            native.cost_per_doc_usd / ours.cost_per_doc_usd
            if native.cost_per_doc_usd and ours.cost_per_doc_usd
            else None
        )
        accuracy = (ours.field_accuracy - native.field_accuracy) * 100
        exact = (ours.exact_match_rate - native.exact_match_rate) * 100
        token_ratio = "n/a" if tokens is None else f"{tokens:.2f}x"
        cost_ratio = "n/a" if cost is None else f"{cost:.2f}x"
        lines.append(
            f"| `{model}` | {token_ratio} | {cost_ratio} | {accuracy:+.1f} pp | {exact:+.1f} pp |"
        )
    return lines


def render_e2e_markdown(report: E2EReport) -> str:
    meta = report.meta
    spent = ", ".join(
        f"{p} {_usd(meta.spent_usd.get(p, 0.0), 2)} of {_usd(b, 2)}"
        for p, b in meta.budget_usd.items()
    )
    lines = [
        f"# End-to-end evaluation: {meta.run_name}",
        "",
        f"- Dataset: `{meta.dataset}`: {meta.documents} invoices, {meta.pages} pages",
        f"- Models: {', '.join(f'`{t}`' for t in meta.targets)}; routes: {', '.join(meta.routes)}",
        f"- Spend: {spent}; skipped calls (budget reached): {meta.skipped_calls}",
        f"- Package `{meta.package_version}`, prompt `{meta.prompt_version}`, "
        f"created {meta.created_at}",
        "",
        "**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. "
        "**native**: the PDF goes to the model as a file. Same prompt, schema, repair turn "
        "and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM "
        "p50 is the model's wall-clock time; the parse CPU time is reported apart, per "
        "document, summed over its pages.",
        "",
        "## All documents",
        "",
        *_HEADER,
        *[_group_row(report, g) for g in report.groups if g.slice == "all"],
        "",
        "### Native against docfunnel",
        "",
        *_comparison(report, "all"),
    ]
    for slice_ in sorted({g.slice for g in report.groups} - {"all"}):
        lines += [
            "",
            f"## {slice_}",
            "",
            *_HEADER,
            *[_group_row(report, g) for g in report.groups if g.slice == slice_],
            "",
            *_comparison(report, slice_),
        ]
    lines.append("")
    return "\n".join(lines)


def write_e2e_report(report: E2EReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / "report.json", out_dir / "report.md"
    json_path.write_text(report.model_dump_json(indent=1) + "\n", encoding="utf-8")
    md_path.write_text(render_e2e_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_e2e_report(path: Path) -> E2EReport:
    return E2EReport.model_validate_json(path.read_text(encoding="utf-8"))
