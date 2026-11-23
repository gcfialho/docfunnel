# Contributing

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (pinned in `.python-version`). Tesseract is optional; without the system binary its tests are skipped.

```bash
make install            # uv sync --all-extras
make check              # ruff, mypy --strict, pytest: what the CI lint-and-test job runs
uvx pre-commit install  # optional: the same checks before every commit
```

`make help` lists every target. Each one is a thin wrapper over `uv run`, so you can always run the underlying command directly.

## Where things go

The package is split by pipeline stage; see [docs/architecture.md](docs/architecture.md) for the full map. In short:

| Change | Code | Tests |
| --- | --- | --- |
| PDF text layer, OCR routing, OCR engines, page pool | `src/docfunnel/parse/` | `tests/parse/` |
| Schema, normalization, business rules, prompts, retry/repair/fallback | `src/docfunnel/extract/` | `tests/extract/` |
| An LLM provider or a model's request parameters | `src/docfunnel/providers/` | `tests/providers/` |
| A metric, a report or a regression gate | `src/docfunnel/evals/` | `tests/evals/` |
| The synthetic generators | `src/docfunnel/datasets/` | `tests/datasets/` |
| Public entry points, sources and downloads | `library.py`, `sources.py` | `tests/library/` |
| CLI, HTTP API, MCP server | `cli.py`, `api.py`, `mcp_server.py` | `tests/interfaces/` |

Shared fixtures live in `tests/conftest.py`; shared helpers (`ScriptedProvider`, paths) in `tests/helpers.py`.

## Conventions

- **Tests never touch the network.** Real providers are tested against stubbed SDK clients and a mock HTTP transport; end-to-end runs use the `fake` provider. CI has no API keys.
- **Types are strict.** `mypy --strict` covers `src/` and `tests/`. Optional dependencies without stubs are listed in `[tool.mypy.overrides]`.
- **Optional dependencies are imported lazily**, inside the function or adapter that needs them, so `import docfunnel` works with no extras.
- **Datasets are generated, not collected.** No real or personal data. Generators are seeded, and a test checks that the committed `data/synthetic/receipts.jsonl` matches the generator.
- **Commits follow [Conventional Commits](https://www.conventionalcommits.org/)** (`feat(parse): ...`, `fix(anthropic): ...`, `docs: ...`), one logical change per commit.

## Changing metrics on purpose

CI compares every run against the committed baselines in `reports/baseline/` and fails on a regression. If a change moves a metric intentionally, regenerate the baseline in the same pull request and say why in the description.

```bash
make baselines   # LLM-step baselines (fake provider, deterministic apart from timestamps and latency)

# Parse-stage baseline: needs RapidOCR and Tesseract, and records the machine it ran on
uv run docfunnel generate-pdfs
uv run docfunnel eval-parse --ocr-engine rapidocr --ocr-engine tesseract \
  --out reports/baseline/parse --run-name "rapidocr+tesseract (<machine>, <N> workers)"
```

Update the result tables in `docs/evaluation/` (and the headline numbers in `README.md`) when the numbers change.

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs four jobs, none of which needs an API key or a GPU:

1. **Lint & test**: ruff, mypy --strict, pytest with coverage (Tesseract installed).
2. **Eval regression gate**: the LLM-step eval with the fake provider, compared against `reports/baseline/fake-mini+fallback`.
3. **Parse-stage eval gate**: regenerates the PDF set, runs RapidOCR on the CPU, compares routing, CER and field recall against `reports/baseline/parse`.
4. **Docker**: builds the image and smoke-tests `extract` and `parse` inside it.

The comparison tables are written to the job summary, and the full reports are uploaded as artifacts.
