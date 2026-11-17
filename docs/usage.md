# Usage

Everything below works offline with the deterministic `fake` provider unless a real provider is named. Run `docfunnel --help` or `docfunnel <command> --help` for every option.

## Install

```bash
uv sync --all-extras        # everything: OCR engines, provider SDKs, MCP, PDF generator
uv sync --extra cpu         # parse stage only: pypdfium2 + RapidOCR
```

| Extra | What it adds |
| --- | --- |
| `pdf` | `pypdfium2`: the PDF text layer |
| `ocr` | `pdf` + RapidOCR on ONNX Runtime (no torch) |
| `tesseract` | `pdf` + `pytesseract` (needs the system binary: `brew install tesseract` / `apt-get install tesseract-ocr`) |
| `cpu` | `pdf` + `ocr` |
| `openai`, `anthropic`, `gemini`, `providers` | provider SDKs (`providers` = all three) |
| `mcp` | the MCP server |
| `synthetic` | ReportLab, Pillow, NumPy: the synthetic PDF generator |

## Commands

| Group | Command | What it does |
| --- | --- | --- |
| Pipeline | `parse FILE` | Pages and blocks, no LLM call. `--format summary\|text\|json\|markdown`, `--ocr-engine`, `--dpi`, `--force-ocr` |
| | `extract FILE\|-` | Validated JSON, review decision and per-call accounting. `--fail-on-review` exits with code 3 |
| Evaluate & gate | `eval-parse` | Parse-stage eval on the synthetic PDF set -> `reports/parse-latest/` |
| | `compare-parse BASE CAND` | Parse regression gate; exit 1 on a quality regression |
| | `eval` | LLM-step eval on the labelled receipts -> `reports/latest/` |
| | `compare BASE CAND` | LLM regression gate; exit 1 when quality drops or cost rises beyond thresholds |
| Datasets | `generate-dataset` | Rewrite `data/synthetic/receipts.jsonl` (seed 7) |
| | `generate-pdfs` | 50 PDFs + `manifest.jsonl` in `data/synthetic/pdf` (seed 11) |
| Serve | `serve` | FastAPI on `127.0.0.1:8000` |
| | `mcp` | MCP server over stdio |

### Parse

```bash
uv run docfunnel parse examples/invoice_mixed_scan.pdf
#   p1: text_layer                 source=text_layer blocks=83 ...
#   p2: ocr:scan_with_stray_text   source=ocr        blocks=30 ...
uv run docfunnel parse examples/invoice_multipage.pdf --format json       # pages, blocks, spans, boxes
uv run docfunnel parse examples/invoice_mixed_scan.pdf --format markdown  # one section per page
```

The two example PDFs are copies of `pdf-037` and `pdf-010` from the generated set. The Markdown export writes a `## Page N` section per page, with a note on pages that came from OCR.

### Extract

```bash
uv run docfunnel extract examples/receipt_us.txt
uv run docfunnel extract examples/receipt_misprinted.txt --fail-on-review   # exit code 3

export OPENAI_API_KEY=...
uv run docfunnel extract examples/invoice_br.txt \
  --provider openai --model gpt-6-luna \
  --fallback anthropic:claude-haiku-5-5
```

PDFs and images go through the parse stage first. See [providers.md](providers.md) for models, prices and what each adapter sends.

## HTTP API

```bash
uv run docfunnel serve            # OpenAPI docs at http://127.0.0.1:8000/docs
curl -s localhost:8000/extract -H 'content-type: application/json' \
  -d "{\"text\": $(jq -Rs . < examples/receipt_us.txt)}"
```

`POST /extract` accepts `{"text": ...}` or `{"path": ...}`. Path input (txt, PDF, or an image) goes through the parse stage and only works inside the directory set by `DOCFUNNEL_INPUT_DIR`; it is disabled by default. `GET /health` is the liveness probe.

## Docker

```bash
docker build -t docfunnel .
docker run --rm -p 8000:8000 docfunnel                     # fake provider
docker run --rm -p 8000:8000 -e DOCFUNNEL_PROVIDER=openai -e OPENAI_API_KEY docfunnel
```

The image includes the PDF text layer but not the OCR extras, to stay small (454 MB on linux/arm64); scanned pages are flagged with `OCR needed but no OCR engine is installed`. It runs as a non-root user with a health check on `/health`.

## MCP server

Stdio transport, for example in an MCP client config:

```json
{
  "mcpServers": {
    "docfunnel": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/docfunnel",
               "--extra", "mcp", "docfunnel", "mcp"],
      "env": { "DOCFUNNEL_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "..." }
    }
  }
}
```

It exposes one tool, `extract_document`, which takes raw text and returns the extraction result (validated fields, issues, review decision and usage totals, without the per-call records).

## Configuration

The CLI, the API and the MCP server read the same environment variables (see [`.env.example`](../.env.example)). CLI flags override them.

| Variable | Meaning | Default |
| --- | --- | --- |
| `DOCFUNNEL_PROVIDER` | `fake`, `openai`, `anthropic`, `gemini` or `replay` | `fake` |
| `DOCFUNNEL_MODEL` | model name | the provider's default |
| `DOCFUNNEL_FALLBACK` | comma-separated `provider:model` chain | none |
| `DOCFUNNEL_MAX_ATTEMPTS` | attempts per model | `3` |
| `DOCFUNNEL_BACKOFF_BASE_S` | base backoff in seconds | `0.5` |
| `DOCFUNNEL_REVIEW_MIN_CONFIDENCE` | fields below this confidence go to review | `0.7` |
| `DOCFUNNEL_PRICING_FILE` | JSON price table overriding the bundled one | bundled |
| `DOCFUNNEL_CASSETTE` | cassette file for the `replay` provider | none |
| `DOCFUNNEL_INPUT_DIR` | directory `POST /extract` may read files from | disabled |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | provider keys | none |
