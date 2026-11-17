# Usage

Everything below works offline with the deterministic `fake` provider unless a real provider is named. Run `docfunnel --help` or `docfunnel <command> --help` for every option.

## Installation

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
| Pipeline | `parse SOURCE` | Pages and blocks, no LLM call. `--format summary\|text\|json\|markdown`, `--ocr-engine`, `--dpi`, `--force-ocr` |
| | `extract SOURCE\|-` | Validated JSON, review decision and per-call accounting. `--fail-on-review` exits with code 3 |
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

PDFs and images go through the parse stage first. See [Providers, models and pricing](providers.md) for models, prices and what each adapter sends.

`SOURCE` is a local path or an http(s) URL; downloads follow the rules under [Configuration](#configuration).

## Python API

```python
import docfunnel

doc = docfunnel.parse_document("examples/invoice_mixed_scan.pdf")  # no LLM call
for page in doc.pages:
    print(page.number, page.route, len(page.text))

result = docfunnel.extract_document("https://example.com/receipt.pdf")
if result.needs_review:
    print(result.review_reasons)
else:
    print(result.document.total, result.document.currency)
```

| Function | What it does |
| --- | --- |
| `parse_document(source, *, options=None, fetch=None, doc_id=None)` | PDF, image or text file to a `ParsedDocument`: pages, blocks, character spans, boxes and the route each page took |
| `extract_document(source=None, *, text=None, extractor=None, settings=None, parse_options=None, fetch=None)` | Receipt or invoice to an `ExtractionResult`: validated fields, issues, `needs_review` with reasons, per-call tokens and cost |
| `aparse_document`, `aextract_document` | The same, run in a worker thread for async code |

`source` is a local path, an http(s) URL or the document's bytes. Bad model output never raises: it ends up in the result with `needs_review=True`. Errors in the input do raise: `SourceError` (not found, not allowed, too large, unknown type) and `ValueError`.

The model comes from `extractor`, else from `settings`, else from the `DOCFUNNEL_*` environment variables. To reuse one configured extractor across calls:

```python
from docfunnel.config import Settings, build_extractor

extractor = build_extractor(
    Settings(provider="openai", fallbacks=(("anthropic", "claude-haiku-5-5"),))
)
results = [docfunnel.extract_document(path, extractor=extractor) for path in paths]
```

`fetch` takes a `docfunnel.FetchPolicy` that sets what a source may point at:

| Field | Default | Meaning |
| --- | --- | --- |
| `allow_local_files` | `True` | Accept local paths |
| `base_dir` | `None` | When set, local paths must stay inside it |
| `allow_urls` | `True` | Download http(s) URLs |
| `allow_private_hosts` | `False` | Allow URLs that resolve to private, loopback, link-local or reserved addresses (checked on every redirect) |
| `allowed_hosts` | `None` | When set, only these host names |
| `max_bytes` | 50 MB | Download size limit |
| `timeout_s` | 30 | Download timeout |
| `max_redirects` | 5 | Redirects to follow |

For pages and blocks without the source handling, use `docfunnel.parse.parse_file` and `docfunnel.parse.PagePool` (many files across worker processes). For the extraction loop on its own, use `docfunnel.extract.Extractor`.

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

It exposes `parse_document` (Markdown per page, no LLM call) and `extract_document` (receipt and invoice fields), both taking a local path or an http(s) URL. Setup for Claude Code, the Claude Agent SDK, the OpenAI Agents SDK, Gemini CLI and LiteLLM is in [Using docfunnel from an agent](agents.md).

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
| `DOCFUNNEL_INPUT_DIR` | directory `POST /extract` and the MCP tools may read files from | API: disabled; MCP: any supported file |
| `DOCFUNNEL_ALLOW_URLS` | let the CLI and the MCP tools download http(s) URLs | `1` |
| `DOCFUNNEL_ALLOW_PRIVATE_URLS` | allow URLs on private, loopback and link-local hosts | `0` |
| `DOCFUNNEL_MAX_DOWNLOAD_MB` | download size limit | `50` |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | provider keys | none |
