# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/). While the version is `0.x`, module paths may change between minor releases.

## [Unreleased]

### Changed

- **Package grouped by pipeline stage.** The extraction modules moved into `docfunnel.extract` (`schema`, `normalize`, `validation`, `prompts`, `extractor`, `pricing`), the generators into `docfunnel.datasets` (`receipts`, `pdfs`, plus `locales` and `scan` split out of them), and the evaluations into `docfunnel.evals.extract` and `docfunnel.evals.parse`. Pieces both evals share are in `docfunnel.evals.{gate,stats,text,formatting}`. Update imports such as `docfunnel.schema` to `docfunnel.extract.schema` and `docfunnel.synthetic_pdf` to `docfunnel.datasets.pdfs`.
- `evals/parse_eval.py` (781 lines) split into `models`, `environment`, `scoring`, `bench`, `runner`, `report` and `compare`; the public API is re-exported from `docfunnel.evals.parse`.
- CLI commands are grouped in `--help` (Pipeline, Evaluate & gate, Datasets, Serve); `compare-parse` takes its defaults from `ParseThresholds`.
- `docfunnel.__version__` is read from the installed package metadata, so `pyproject.toml` is the only place the version is set.
- Tests mirror the package layout (`tests/parse`, `tests/extract`, `tests/providers`, `tests/evals`, `tests/datasets`, `tests/interfaces`).
- README shortened to an overview; details moved to `docs/` (architecture, usage, providers, both evaluations, roadmap).
- Pipeline diagrams redrawn: one subgraph per stage, one node shape per role, and colours that read on light and dark backgrounds. Schema errors loop back to the model; business-rule failures go to review.
- Error messages for a missing extra, API key, cassette or Tesseract binary now include the command or flag that fixes them.

### Added

- `Makefile` with `install`, `check`, `eval`, `gate`, `eval-parse`, `gate-parse`, `baselines`, `docker` and other targets.
- `CONTRIBUTING.md`, this changelog, `.pre-commit-config.yaml`, `.editorconfig`, Dependabot for GitHub Actions and uv, issue and pull request templates.
- Cross-platform parse results, including the x86_64 GitHub runner, in `docs/evaluation/parse-stage.md`.

## [0.1.0] - 2026-11-03

First public version.

### Added

- **Parse stage:** pypdfium2 text layer with per-page OCR routing, RapidOCR and Tesseract on the CPU, a page-level process pool, and JSON, text and Markdown output.
- **Synthetic PDFs:** seeded multi-page invoices and contracts in four locales, with digital, scanned and mixed variants and page-level ground truth.
- **Parse-stage eval and CI gate:** OCR routing precision and recall, CER and WER by noise level, field recall and throughput with the hardware recorded.
- **LLM extraction:** Pydantic contract, shared normalization, business rules and review routing, repair prompts, backoff, fallback chains, per-call cost and latency.
- **Providers:** OpenAI, Anthropic and Gemini with native structured output and per-model reasoning settings; an offline `fake` provider with fault injection; record and replay cassettes.
- **LLM-step eval and CI gate:** field accuracy, exact match, schema compliance, hallucination rate, review precision and recall, cost and latency.
- **Interfaces:** CLI, FastAPI service, MCP server and Docker image.
- `mypy --strict` over `src/` and `tests/`.

[Unreleased]: https://github.com/gcfialho/docfunnel/compare/94fa020...HEAD
[0.1.0]: https://github.com/gcfialho/docfunnel/tree/94fa020
