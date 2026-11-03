"""Command-line interface for extraction, evaluation, comparison and serving."""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from docfunnel.config import Settings, build_extractor, parse_target
from docfunnel.evals.compare import Thresholds, compare_reports, render_comparison
from docfunnel.evals.dataset import DEFAULT_DATASET, file_sha256, load_dataset
from docfunnel.evals.report import load_report, summary_rows, write_report
from docfunnel.evals.runner import run_eval
from docfunnel.extractor import ModelTarget
from docfunnel.loaders import UnsupportedDocumentError, load_document
from docfunnel.providers.base import ProviderNotConfiguredError
from docfunnel.providers.replay import RecordingProvider

app = typer.Typer(
    help="LLM structured extraction for receipts/invoices, with an evaluation harness.",
    no_args_is_help=True,
    add_completion=False,
)

ProviderOpt = Annotated[
    str | None,
    typer.Option(
        "--provider",
        "-p",
        help="fake | openai | anthropic | gemini | replay [env: DOCFUNNEL_PROVIDER]",
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


@app.callback()
def _main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


@app.command()
def extract(
    source: Annotated[str, typer.Argument(help="File (txt/pdf/image) or '-' for stdin")],
    provider: ProviderOpt = None,
    model: ModelOpt = None,
    fallback: FallbackOpt = None,
    cassette: CassetteOpt = None,
    include_calls: Annotated[bool, typer.Option(help="Include per-call accounting")] = True,
    fail_on_review: Annotated[
        bool, typer.Option(help="Exit with code 3 when the result needs human review")
    ] = False,
) -> None:
    """Extract one document and print the result as JSON."""
    try:
        text = sys.stdin.read() if source == "-" else load_document(Path(source))
        extractor = build_extractor(_settings(provider, model, fallback, cassette))
        result = extractor.extract(text)
    except (OSError, UnsupportedDocumentError, ProviderNotConfiguredError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    exclude = None if include_calls else {"calls"}
    typer.echo(result.model_dump_json(indent=2, exclude=exclude))
    if fail_on_review and result.needs_review:
        raise typer.Exit(3)


@app.command("eval")
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
    json_path, md_path = write_report(report, out)
    width = max(len(name) for name, _ in summary_rows(report))
    for name, value in summary_rows(report):
        typer.echo(f"{name:<{width}}  {value}")
    typer.echo(f"\nWrote {json_path} and {md_path}")


@app.command()
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
    typer.echo(markdown)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
    if not comparison.passed:
        raise typer.Exit(1)


OcrEngineOpt = Annotated[
    str, typer.Option("--ocr-engine", help="auto | none | rapidocr | tesseract")
]


@app.command()
def parse(
    source: Annotated[Path, typer.Argument(help="File (pdf/image/txt)")],
    ocr_engine: OcrEngineOpt = "auto",
    dpi: Annotated[int, typer.Option(help="Render resolution for OCR")] = 200,
    force_ocr: Annotated[
        bool, typer.Option(help="OCR every page, ignoring the text layer")
    ] = False,
    output: Annotated[str, typer.Option("--format", help="summary | text | json")] = "summary",
) -> None:
    """Parse one document into pages and blocks (no LLM call)."""
    from docfunnel.parse import ParseOptions, parse_file
    from docfunnel.parse.ocr import OcrUnavailableError

    if output not in {"summary", "text", "json"}:
        raise _fail("--format must be summary, text or json")
    try:
        options = ParseOptions(ocr_engine=ocr_engine, dpi=dpi, force_ocr=force_ocr)
        document = parse_file(source, options)
    except (OSError, UnsupportedDocumentError, OcrUnavailableError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    if output == "json":
        typer.echo(document.model_dump_json(indent=2))
        return
    if output == "text":
        typer.echo(document.text)
        return
    typer.echo(f"{document.doc_id}: {len(document.pages)} page(s), parser {document.parser}")
    for page in document.pages:
        total = page.timings_ms.get("total", 0.0)
        line = (
            f"  p{page.number}: {page.route:<26} source={page.source:<10} "
            f"blocks={len(page.blocks):<4} chars={len(page.text):<6} {total:8.1f} ms"
        )
        typer.echo(line + (f"  error: {page.error}" if page.error else ""))


@app.command("generate-dataset")
def generate_dataset(
    out: Annotated[Path, typer.Option(help="Output JSONL path")] = DEFAULT_DATASET,
    n: Annotated[int, typer.Option(help="Number of documents")] = 60,
    seed: Annotated[int, typer.Option(help="Random seed")] = 7,
) -> None:
    """(Re)generate the synthetic labelled dataset deterministically."""
    from docfunnel.synthetic import write_dataset

    count = write_dataset(out, n=n, seed=seed)
    typer.echo(f"Wrote {count} documents to {out}")


@app.command("generate-pdfs")
def generate_pdfs(
    out: Annotated[Path, typer.Option(help="Output directory (PDFs + manifest.jsonl)")] = Path(
        "data/synthetic/pdf"
    ),
    n: Annotated[int, typer.Option(help="Number of documents")] = 50,
    seed: Annotated[int, typer.Option(help="Random seed")] = 11,
) -> None:
    """Generate multi-page invoice/contract PDFs (digital, scanned, mixed) with ground truth."""
    try:
        from docfunnel.synthetic_pdf import write_pdf_dataset
    except ImportError as exc:  # pragma: no cover - only without the extra
        raise _fail("generate-pdfs requires the 'synthetic' extra") from exc
    truths = write_pdf_dataset(out, n=n, seed=seed)
    pages = sum(len(t.pages) for t in truths)
    scanned = sum(p.scanned for t in truths for p in t.pages)
    typer.echo(f"Wrote {len(truths)} documents ({pages} pages, {scanned} scanned) to {out}")


@app.command("eval-parse")
def eval_parse(
    data: Annotated[Path, typer.Option(help="Directory from generate-pdfs")] = Path(
        "data/synthetic/pdf"
    ),
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
    from docfunnel.evals.parse_eval import (
        ParseEvalConfig,
        run_parse_eval,
        summary_rows,
        write_parse_report,
    )

    if not (data / "manifest.jsonl").is_file():
        raise _fail(f"{data}/manifest.jsonl not found; run 'docfunnel generate-pdfs' first")
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
    json_path, md_path = write_parse_report(report, out)
    rows = summary_rows(report)
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        typer.echo(f"{name:<{width}}  {value}")
    typer.echo(f"\nWrote {json_path} and {md_path}")


@app.command("compare-parse")
def compare_parse(
    baseline: Annotated[Path, typer.Argument(help="Baseline parse report.json")],
    candidate: Annotated[Path, typer.Argument(help="Candidate parse report.json")],
    max_routing_drop: float = 0.0,
    max_digital_cer_increase: float = 0.001,
    max_scanned_cer_increase: float = 0.01,
    max_field_recall_drop: float = 0.02,
    min_speedup_vs_pypdf: Annotated[
        float | None, typer.Option(help="pypdfium2 vs pypdf in the candidate run; 0 disables")
    ] = 3.0,
    out: Annotated[Path | None, typer.Option(help="Also write the comparison as Markdown")] = None,
) -> None:
    """Compare two parse eval runs; exit 1 on a quality regression."""
    from docfunnel.evals.parse_eval import (
        ParseThresholds,
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
    typer.echo(markdown)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
    if not comparison.passed:
        raise typer.Exit(1)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the FastAPI server."""
    import uvicorn

    uvicorn.run("docfunnel.api:app", host=host, port=port)


@app.command("mcp")
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
