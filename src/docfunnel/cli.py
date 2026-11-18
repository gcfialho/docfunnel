"""``docfunnel`` command line: parse, extract, evaluate, generate datasets, serve.

Commands are grouped in the help output the same way the package is laid out:
pipeline stages first, then their evaluations and regression gates, then the
dataset generators and the servers.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from docfunnel.config import Settings, build_extractor, parse_target
from docfunnel.datasets.pdfs import DEFAULT_PDF_DIR, MANIFEST_NAME
from docfunnel.evals.extract.compare import Thresholds, compare_reports, render_comparison
from docfunnel.evals.extract.dataset import DEFAULT_DATASET, file_sha256, load_dataset
from docfunnel.evals.extract.report import load_report, summary_rows, write_report
from docfunnel.evals.extract.runner import run_eval
from docfunnel.evals.parse.compare import ParseThresholds
from docfunnel.extract.extractor import ModelTarget
from docfunnel.library import extract_document
from docfunnel.loaders import UnsupportedDocumentError
from docfunnel.providers.base import ProviderNotConfiguredError
from docfunnel.providers.replay import RecordingProvider

app = typer.Typer(
    help=(
        "CPU-first document pipeline: parse PDFs and scans page by page (OCR only where "
        "needed), extract validated JSON with an LLM, and evaluate every stage."
    ),
    no_args_is_help=True,
    add_completion=False,
)

PIPELINE = "Pipeline"
EVALUATE = "Evaluate & gate"
DATASETS = "Datasets"
SERVE = "Serve"

ProviderOpt = Annotated[
    str | None,
    typer.Option(
        "--provider",
        "-p",
        help="fake | openai | anthropic | gemini | ollama | replay [env: DOCFUNNEL_PROVIDER]",
    ),
]
ModelOpt = Annotated[
    str | None, typer.Option("--model", "-m", help="Model name [env: DOCFUNNEL_MODEL]")
]
FallbackOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--fallback",
        "-f",
        help="Fallback target 'provider:model' (repeatable) [env: DOCFUNNEL_FALLBACK]",
    ),
]
CassetteOpt = Annotated[
    Path | None,
    typer.Option(
        "--cassette", help="Cassette file for the replay provider [env: DOCFUNNEL_CASSETTE]"
    ),
]


def _settings(
    provider: str | None, model: str | None, fallback: list[str] | None, cassette: Path | None
) -> Settings:
    settings = Settings.from_env()
    if provider and provider != settings.provider:
        # Switching provider resets the model to that provider's default.
        settings = replace(settings, provider=provider, model=None)
    settings = settings.with_overrides(model=model, cassette=cassette)
    if fallback is not None:
        settings = settings.with_overrides(fallbacks=tuple(parse_target(f) for f in fallback))
    return settings


def _fail(message: str, code: int = 2) -> typer.Exit:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code)


def _print_summary(rows: list[tuple[str, str]], written: tuple[Path, Path]) -> None:
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        typer.echo(f"{name:<{width}}  {value}")
    typer.echo(f"\nWrote {written[0]} and {written[1]}")


def _emit_markdown(markdown: str, out: Path | None) -> None:
    typer.echo(markdown)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")


@app.callback()
def _main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Log retries, fallbacks and progress")
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


OcrEngineOpt = Annotated[
    str, typer.Option("--ocr-engine", help="auto | none | rapidocr | tesseract")
]


@app.command(rich_help_panel=PIPELINE)
def parse(
    source: Annotated[str, typer.Argument(help="File path or http(s) URL (pdf/image/txt)")],
    ocr_engine: OcrEngineOpt = "auto",
    dpi: Annotated[int, typer.Option(help="Render resolution for OCR")] = 200,
    force_ocr: Annotated[
        bool, typer.Option(help="OCR every page, ignoring the text layer")
    ] = False,
    output: Annotated[
        str, typer.Option("--format", help="summary | text | json | markdown")
    ] = "summary",
) -> None:
    """Parse one document into pages and blocks (no LLM call)."""
    from docfunnel.library import parse_document
    from docfunnel.parse import ParseOptions, to_markdown
    from docfunnel.parse.ocr import OcrUnavailableError

    if output not in {"summary", "text", "json", "markdown"}:
        raise _fail("--format must be summary, text, json or markdown")
    try:
        options = ParseOptions(ocr_engine=ocr_engine, dpi=dpi, force_ocr=force_ocr)
        fetch = Settings.from_env().fetch_policy(confine_to_input_dir=False)
        document = parse_document(source, options=options, fetch=fetch)
    except (OSError, UnsupportedDocumentError, OcrUnavailableError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    if output == "json":
        typer.echo(document.model_dump_json(indent=2))
        return
    if output == "text":
        typer.echo(document.text)
        return
    if output == "markdown":
        typer.echo(to_markdown(document), nl=False)
        return
    typer.echo(f"{document.doc_id}: {len(document.pages)} page(s), parser {document.parser}")
    for page in document.pages:
        total = page.timings_ms.get("total", 0.0)
        line = (
            f"  p{page.number}: {page.route:<26} source={page.source:<10} "
            f"blocks={len(page.blocks):<4} chars={len(page.text):<6} {total:8.1f} ms"
        )
        typer.echo(line + (f"  error: {page.error}" if page.error else ""))


@app.command(rich_help_panel=PIPELINE)
def extract(
    source: Annotated[
        str, typer.Argument(help="File path, http(s) URL (txt/pdf/image) or '-' for stdin")
    ],
    provider: ProviderOpt = None,
    model: ModelOpt = None,
    fallback: FallbackOpt = None,
    cassette: CassetteOpt = None,
    route: Annotated[
        str | None,
        typer.Option(
            help="What the model is sent: text | hybrid | hybrid-ocr | native "
            "[env: DOCFUNNEL_ROUTE; default: text]"
        ),
    ] = None,
    include_calls: Annotated[bool, typer.Option(help="Include per-call accounting")] = True,
    fail_on_review: Annotated[
        bool, typer.Option(help="Exit with code 3 when the result needs human review")
    ] = False,
) -> None:
    """Extract one document and print the result as JSON."""
    try:
        settings = _settings(provider, model, fallback, cassette)
        extractor = build_extractor(settings)
        if source == "-":
            result = extract_document(text=sys.stdin.read(), extractor=extractor)
        else:
            fetch = settings.fetch_policy(confine_to_input_dir=False)
            result = extract_document(
                source, extractor=extractor, fetch=fetch, route=route or settings.route
            )
    except (OSError, UnsupportedDocumentError, ProviderNotConfiguredError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    exclude = None if include_calls else {"calls"}
    typer.echo(result.model_dump_json(indent=2, exclude=exclude))
    if fail_on_review and result.needs_review:
        raise typer.Exit(3)


@app.command("eval-parse", rich_help_panel=EVALUATE)
def eval_parse(
    data: Annotated[Path, typer.Option(help="Directory from generate-pdfs")] = DEFAULT_PDF_DIR,
    out: Annotated[Path, typer.Option(help="Output directory for report.json/report.md")] = Path(
        "reports/parse-latest"
    ),
    ocr_engine: Annotated[
        list[str] | None,
        typer.Option("--ocr-engine", help="auto | none | rapidocr | tesseract (repeatable)"),
    ] = None,
    workers: Annotated[int | None, typer.Option(help="Worker processes (default: CPUs)")] = None,
    ocr_threads: Annotated[int, typer.Option(help="ONNX Runtime threads per worker")] = 1,
    dpi: Annotated[int, typer.Option(help="Render resolution for OCR")] = 200,
    run_name: Annotated[str | None, typer.Option(help="Name shown in reports")] = None,
) -> None:
    """Evaluate the parse stage: OCR routing, CER/WER, field recall and throughput."""
    from docfunnel.evals.parse import (
        ParseEvalConfig,
        run_parse_eval,
        summary_rows,
        write_parse_report,
    )

    if not (data / MANIFEST_NAME).is_file():
        raise _fail(f"{data}/{MANIFEST_NAME} not found; run 'docfunnel generate-pdfs' first")
    config = ParseEvalConfig(
        dataset=data,
        engines=ocr_engine or ["auto"],
        workers=workers,
        ocr_threads=ocr_threads,
        dpi=dpi,
        run_name=run_name,
    )
    try:
        report = run_parse_eval(config)
    except (ImportError, ValueError, RuntimeError) as exc:
        raise _fail(str(exc)) from exc
    _print_summary(summary_rows(report), write_parse_report(report, out))


@app.command("compare-parse", rich_help_panel=EVALUATE)
def compare_parse(
    baseline: Annotated[Path, typer.Argument(help="Baseline parse report.json")],
    candidate: Annotated[Path, typer.Argument(help="Candidate parse report.json")],
    max_routing_drop: float | None = ParseThresholds.max_routing_drop,
    max_digital_cer_increase: float | None = ParseThresholds.max_digital_cer_increase,
    max_scanned_cer_increase: float | None = ParseThresholds.max_scanned_cer_increase,
    max_field_recall_drop: float | None = ParseThresholds.max_field_recall_drop,
    min_speedup_vs_pypdf: Annotated[
        float | None, typer.Option(help="pypdfium2 vs pypdf in the candidate run; 0 disables")
    ] = ParseThresholds.min_speedup_vs_pypdf,
    out: Annotated[Path | None, typer.Option(help="Also write the comparison as Markdown")] = None,
) -> None:
    """Compare two parse eval runs; exit 1 on a quality regression."""
    from docfunnel.evals.parse import (
        compare_parse_reports,
        load_parse_report,
        render_parse_comparison,
    )

    try:
        base, cand = load_parse_report(baseline), load_parse_report(candidate)
    except (OSError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    thresholds = ParseThresholds(
        max_routing_drop=max_routing_drop,
        max_digital_cer_increase=max_digital_cer_increase,
        max_scanned_cer_increase=max_scanned_cer_increase,
        max_field_recall_drop=max_field_recall_drop,
        min_speedup_vs_pypdf=min_speedup_vs_pypdf or None,
    )
    comparison = compare_parse_reports(base, cand, thresholds)
    markdown = render_parse_comparison(comparison, base, cand)
    _emit_markdown(markdown, out)
    if not comparison.passed:
        raise typer.Exit(1)


@app.command("eval", rich_help_panel=EVALUATE)
def eval_command(
    dataset: Annotated[Path, typer.Option(help="Labelled JSONL dataset")] = DEFAULT_DATASET,
    out: Annotated[Path, typer.Option(help="Output directory for report.json/report.md")] = Path(
        "reports/latest"
    ),
    provider: ProviderOpt = None,
    model: ModelOpt = None,
    fallback: FallbackOpt = None,
    cassette: CassetteOpt = None,
    record: Annotated[
        Path | None,
        typer.Option(help="Record every response of the primary model to this cassette"),
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Only evaluate the first N documents")] = None,
    workers: Annotated[int, typer.Option(help="Concurrent documents")] = 1,
    run_name: Annotated[str | None, typer.Option(help="Name shown in reports")] = None,
) -> None:
    """Run extraction over a labelled dataset and write JSON + Markdown reports."""
    try:
        settings = _settings(provider, model, fallback, cassette)
        extractor = build_extractor(settings)
        documents = load_dataset(dataset, limit=limit)
    except (OSError, ProviderNotConfiguredError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    if record is not None:
        primary = extractor.targets[0]
        extractor.targets[0] = ModelTarget(
            RecordingProvider(primary.provider, record), primary.model
        )

    done = 0
    interactive = sys.stderr.isatty()

    def progress(*_: object) -> None:
        nonlocal done
        done += 1
        if interactive:
            typer.echo(f"\r  {done}/{len(documents)} documents", nl=False, err=True)

    provider_name, model_name = settings.primary
    report = run_eval(
        extractor,
        documents,
        run_name=run_name or f"{provider_name}:{model_name}",
        dataset=dataset.as_posix(),
        dataset_sha256=file_sha256(dataset),
        workers=workers,
        on_result=progress,
    )
    if interactive:
        typer.echo("", err=True)
    _print_summary(summary_rows(report), write_report(report, out))


@app.command(rich_help_panel=EVALUATE)
def compare(
    baseline: Annotated[Path, typer.Argument(help="Baseline report.json")],
    candidate: Annotated[Path, typer.Argument(help="Candidate report.json")],
    max_accuracy_drop: float | None = Thresholds.max_accuracy_drop,
    max_exact_match_drop: float | None = Thresholds.max_exact_match_drop,
    max_schema_compliance_drop: float | None = Thresholds.max_schema_compliance_drop,
    max_hallucination_increase: float | None = Thresholds.max_hallucination_increase,
    max_review_recall_drop: float | None = Thresholds.max_review_recall_drop,
    max_cost_increase: Annotated[
        float | None, typer.Option(help="Relative, e.g. 0.2 = +20%")
    ] = Thresholds.max_cost_increase,
    max_p95_latency_increase: Annotated[
        float | None, typer.Option(help="Relative; disabled unless set (wall-clock is noisy in CI)")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Also write the comparison as Markdown")] = None,
) -> None:
    """Compare two eval runs; exit 1 if the candidate regresses beyond thresholds."""
    try:
        base, cand = load_report(baseline), load_report(candidate)
    except (OSError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    thresholds = Thresholds(
        max_accuracy_drop=max_accuracy_drop,
        max_exact_match_drop=max_exact_match_drop,
        max_schema_compliance_drop=max_schema_compliance_drop,
        max_hallucination_increase=max_hallucination_increase,
        max_review_recall_drop=max_review_recall_drop,
        max_cost_increase=max_cost_increase,
        max_p95_latency_increase=max_p95_latency_increase,
    )
    comparison = compare_reports(base, cand, thresholds)
    markdown = render_comparison(comparison, base, cand)
    _emit_markdown(markdown, out)
    if not comparison.passed:
        raise typer.Exit(1)


@app.command("generate-dataset", rich_help_panel=DATASETS)
def generate_dataset(
    out: Annotated[Path, typer.Option(help="Output JSONL path")] = DEFAULT_DATASET,
    n: Annotated[int, typer.Option(help="Number of documents")] = 60,
    seed: Annotated[int, typer.Option(help="Random seed")] = 7,
) -> None:
    """Regenerate the labelled receipt dataset (seeded, so the output is identical)."""
    from docfunnel.datasets.receipts import write_dataset

    count = write_dataset(out, n=n, seed=seed)
    typer.echo(f"Wrote {count} documents to {out}")


@app.command("generate-pdfs", rich_help_panel=DATASETS)
def generate_pdfs(
    out: Annotated[
        Path, typer.Option(help="Output directory (PDFs + manifest.jsonl)")
    ] = DEFAULT_PDF_DIR,
    n: Annotated[int, typer.Option(help="Number of documents")] = 50,
    seed: Annotated[int, typer.Option(help="Random seed")] = 11,
) -> None:
    """Generate multi-page invoice/contract PDFs (digital, scanned, mixed) with ground truth."""
    from docfunnel.datasets.pdfs import write_pdf_dataset

    try:
        truths = write_pdf_dataset(out, n=n, seed=seed)
    except ImportError as exc:  # pragma: no cover - only without the extra
        raise _fail(
            "generate-pdfs requires the 'synthetic' extra: uv sync --extra synthetic"
        ) from exc
    pages = sum(len(t.pages) for t in truths)
    scanned = sum(p.scanned for t in truths for p in t.pages)
    typer.echo(f"Wrote {len(truths)} documents ({pages} pages, {scanned} scanned) to {out}")


@app.command("generate-e2e", rich_help_panel=DATASETS)
def generate_e2e(
    data: Annotated[Path, typer.Option(help="Directory from generate-pdfs")] = DEFAULT_PDF_DIR,
    out: Annotated[Path, typer.Option(help="Output directory (PDFs + e2e.jsonl)")] = Path(
        "data/synthetic/e2e"
    ),
    large: Annotated[int, typer.Option(help="Invoices with contracts annexed (8+ pages)")] = 10,
    seed: Annotated[int, typer.Option(help="Random seed")] = 5,
) -> None:
    """Build the end-to-end PDF set: the generated invoices plus large ones with annexes."""
    from docfunnel.evals.e2e import build_e2e_set

    if not (data / MANIFEST_NAME).is_file():
        raise _fail(f"{data}/{MANIFEST_NAME} not found; run 'docfunnel generate-pdfs' first")
    docs = build_e2e_set(data, out, n_large=large, seed=seed)
    pages = sum(d.pages for d in docs)
    sizes = {s: sum(d.size == s for d in docs) for s in ("small", "large")}
    typer.echo(
        f"Wrote {len(docs)} invoices ({sizes['small']} small, {sizes['large']} large; "
        f"{pages} pages) to {out}"
    )


@app.command("eval-e2e", rich_help_panel=EVALUATE)
def eval_e2e(
    target: Annotated[
        list[str], typer.Option("--target", "-t", help="provider:model to test (repeatable)")
    ],
    data: Annotated[Path, typer.Option(help="Directory from generate-e2e")] = Path(
        "data/synthetic/e2e"
    ),
    out: Annotated[Path, typer.Option(help="Output directory for report.json/report.md")] = Path(
        "reports/e2e-latest"
    ),
    route: Annotated[
        list[str] | None,
        typer.Option("--route", help="docfunnel | native | hybrid | hybrid-ocr (repeatable)"),
    ] = None,
    budget_usd: Annotated[
        float, typer.Option(help="Spending cap per provider; later calls are skipped")
    ] = 4.0,
    limit: Annotated[int | None, typer.Option(help="Only the first N documents")] = None,
    sample: Annotated[
        int | None, typer.Option(help="A seeded random sample of N documents (seed 0)")
    ] = None,
    where: Annotated[
        list[str] | None,
        typer.Option(help="Only documents with this tag, e.g. scan=has_scanned_pages, size=large"),
    ] = None,
    workers: Annotated[int, typer.Option(help="Concurrent documents per model")] = 4,
    compact_output: Annotated[
        bool, typer.Option(help="One-letter line-item keys in the model's answer")
    ] = False,
    run_name: Annotated[str | None, typer.Option(help="Name shown in reports")] = None,
) -> None:
    """Compare the docfunnel route (CPU parse, then text) with native PDF input, per model.

    Targets accept variant options for ablations, e.g.
    ``gemini:gemini-3.8-flash+thinking_level=medium`` or
    ``anthropic:claude-haiku-5-5+effort=medium``.
    """
    from docfunnel.evals.e2e import DEFAULT_ROUTES, ROUTES, E2EConfig, run_e2e, write_e2e_report

    routes = tuple(route or DEFAULT_ROUTES)
    if unknown := set(routes) - set(ROUTES):
        raise _fail(f"unknown route(s) {sorted(unknown)}; use docfunnel, native or hybrid")
    config = E2EConfig(
        dataset=data,
        targets=[parse_target(t) for t in target],
        routes=routes,
        default_budget_usd=budget_usd,
        limit=limit,
        where=dict(w.split("=", 1) for w in where or []),
        compact_output=compact_output,
        sample=sample,
        workers=workers,
        run_name=run_name,
    )
    interactive = sys.stderr.isatty()
    done = 0

    def progress(*_: object) -> None:
        nonlocal done
        done += 1
        if interactive:
            typer.echo(f"\r  {done} calls", nl=False, err=True)

    try:
        report = run_e2e(config, on_row=progress)
    except (OSError, ValueError, ProviderNotConfiguredError) as exc:
        raise _fail(str(exc)) from exc
    if interactive:
        typer.echo("", err=True)
    json_path, md_path = write_e2e_report(report, out)
    spent = ", ".join(f"{p} ${v:.4f}" for p, v in report.meta.spent_usd.items())
    typer.echo(f"Spent: {spent or '$0'}; skipped calls: {report.meta.skipped_calls}")
    typer.echo(f"Wrote {json_path} and {md_path}")


@app.command(rich_help_panel=SERVE)
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the HTTP API (FastAPI, OpenAPI docs at /docs)."""
    import uvicorn

    uvicorn.run("docfunnel.api:app", host=host, port=port)


@app.command("mcp", rich_help_panel=SERVE)
def mcp_command() -> None:
    """Run the MCP server over stdio (requires the 'mcp' extra)."""
    from docfunnel.mcp_server import build_server

    try:
        server = build_server()
    except RuntimeError as exc:
        raise _fail(str(exc)) from exc
    server.run()


if __name__ == "__main__":  # pragma: no cover
    app()
