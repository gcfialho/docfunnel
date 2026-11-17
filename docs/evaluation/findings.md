# Findings from real-model runs

A lab notebook: what each run with a real model showed, what it cost, and what changed in the code because of it. Newest entries first. Raw reports are in [`reports/e2e/`](../../reports/e2e/).

Spend so far (cap: US$ 5 per provider key): Gemini ~US$ 2.78, Anthropic ~US$ 0.32.

## 2026-11-17: full run, 4 models x 2 routes x 39 invoices

**Setup.** `docfunnel eval-e2e` on 39 invoices, 174 pages: 29 small (1 to 4 pages, 17 to 170 line items) and 10 large (an invoice with contracts annexed, 8 to 10 pages); 10 fully digital, 29 with at least one scanned page. Models: Gemini 3.5 Flash-Lite (thinking `minimal`), 3.8 Flash (`low`), 3.1 Flash-Lite (default), Claude Haiku 5.5 (effort `low`). Output limit 16,384 tokens, 2 attempts. Cost: Gemini US$ 2.67, Anthropic US$ 0.29; no call skipped. Report: [`reports/e2e/report.md`](../../reports/e2e/report.md).

| Model | Route | Field accuracy | Exact match | Line items F1 | Cost per 1k docs | LLM p50 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | docfunnel | 99.4% | 69.2% | 97.3% | $12.46 | 7.3 s |
| `gemini-3.5-flash-lite` | native | 99.7% | **97.4%** | 100.0% | $11.86 | 8.5 s |
| `gemini-3.8-flash` | docfunnel | 99.4% | 64.1% | 95.7% | $15.20 | 17.1 s |
| `gemini-3.8-flash` | native | 100.0% | **97.4%** | 100.0% | $14.40 | 19.8 s |
| `claude-haiku-5-5` | docfunnel | 98.0% | 69.2% | 92.7% | **$3.21** | 16.0 s |
| `claude-haiku-5-5` | native | 100.0% | 82.1% | 86.5% | $4.29 | 17.6 s |
| `gemini-3.1-flash-lite` | docfunnel | 99.1% | 87.2% | 99.1% | $7.39 | 8.0 s |
| `gemini-3.1-flash-lite` | native | 99.7% | 84.6% | 98.4% | $7.10 | 9.3 s |

The docfunnel route also spends parse CPU: 0.8 s per digital document, 26 s per document with scans (RapidOCR, summed over pages; wall-clock is lower across the page pool).

### What it shows

1. **The parse stage is right on digital pages and wrong on scans.** Every docfunnel miss, on every model, is on a document with scanned pages; on the 10 digital documents the docfunnel route is as good or better than native (exact match +10 pp on Gemini, +30 pp on Haiku, whose native line-item F1 drops to 74%). On documents with scans, native wins by 28 to 48 pp of exact match on Gemini 3.5 / 3.8: the model reading the scan beats RapidOCR text. Header fields stay at 97 to 100% either way; the misses are line items.
2. **On Gemini, the parse stage does not save money.** Gemini reads a PDF page in ~600 tokens, fewer than its extracted text plus our prompt (native input 0.63x on digital, 0.94x on large documents). Native is 2 to 6% cheaper on all three Gemini models.
3. **On Claude it does, and more as documents grow.** Native input is 1.6x the docfunnel input on small documents and 2.2x on large ones; cost 1.25x and 1.63x.
4. **Output is 72 to 92% of the cost**, on every model and both routes: line items plus thinking. The parse stage only touches input, so the biggest cost lever left is output (compact line-item format, thinking level), not parsing.
5. **A bigger model did not help.** Gemini 3.8 Flash matches 3.5 Flash-Lite's accuracy (97.4% exact match native), costs 21% more and is 2.3x slower.
6. **Cost-benefit ranking** (exact match / cost per 1k docs): Haiku 5.5 docfunnel 69% / $3.21; Haiku 5.5 native 82% / $4.29; Gemini 3.1 Flash-Lite native 85% / $7.10 (docfunnel 87% / $7.39); Gemini 3.5 Flash-Lite native 97% / $11.86.

### What to change or test next

- **Hybrid route** (built, `--route hybrid`): text for text-layer pages, an image only for pages routed to OCR. If finding 1 holds, it should keep the docfunnel result on digital pages and the native result on scans, at native-like cost on Claude.
- **Output tokens:** measure how much is thinking, then try a compact line-item format.
- **More models** as quality references: Gemini 3.6 Flash, Claude Sonnet 5.5, on a subset.

## 2026-11-17: first calls, smoke test and 3-document pilot

**Setup.** Models available to the keys on 2026-11-17: Gemini 3.8 / 3.7 / 3.6 Flash, 3.5 / 3.1 Flash-Lite; Claude Haiku 5.5. One receipt per model on the text route, then the end-to-end eval (`docfunnel eval-e2e`) on 3 small invoices (2 to 4 pages, 21 to 170 line items), both routes. Pilot cost: US$ 0.10.

### Bugs the first real calls found (fixed)

| Finding | Effect before the fix | Fix |
| --- | --- | --- |
| Anthropic structured outputs accept at most 16 union-typed parameters; the strict schema had 21 (every `field_confidence` score was `number \| null`) | **Every** call to `claude-haiku-5-5`, the default Anthropic model, failed with HTTP 400 | Scores are plain numbers, 0 for an absent field (prompt v2); a test keeps the schema under the limit |
| A 170-line invoice needs ~6k tokens of JSON plus thinking; the output limit was 8,192 | Truncated JSON, two failed attempts, no result (Haiku, native route) | `DOCFUNNEL_MAX_OUTPUT_TOKENS`; the e2e eval uses 16,384 on both routes |
| Haiku returned an invoice with every header field right and **no line items** (144 missing) | Auto-accepted: the sum rule only ran when items were present | New error `line_items_missing` when a subtotal is present and the list is empty |
| `gemini-2.5-flash-lite` is listed by the API but "no longer available to new users" (HTTP 404) | Cannot be benchmarked with a new key | Dropped from the runs; kept in the tables for existing keys |

The offline tests (stubbed SDKs, a mock HTTP transport) had checked the request shape, not what the live APIs accept. Each of these needed one real call to find.

### What the pilot suggests (3 documents: a hypothesis, not a result)

| Model | Route | Field accuracy | Line items F1 | Input tok/doc | Output tok/doc | Cost/doc | LLM p50 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | docfunnel | 96.3% | 89.1% | 3,426 | 4,931 | $0.0134 | 10.4 s |
| `gemini-3.5-flash-lite` | native | 96.3% | 100.0% | 2,236 | 4,782 | $0.0126 | 8.3 s |
| `claude-haiku-5-5` | docfunnel | 100.0% | 64.2% | 5,156 | 3,874 | $0.0025 | 13.7 s |
| `claude-haiku-5-5` | native | 66.7% | 66.2% | 13,812 | 9,068 | $0.0059 | 22.0 s |

The docfunnel route also spent 5.8 s of CPU per document parsing (OCR on scanned pages).

1. **Output, not input, drives the cost of invoice extraction.** Line items plus thinking are 4k to 8k output tokens per invoice, against 2k to 7k input tokens. The parse stage reduces input; output is the same on both routes. The lever is smaller than expected for line-item-heavy documents.
2. **The parse stage pays off on Claude, not on Gemini.** Gemini reads a digital PDF in fewer tokens than its extracted text plus our prompt (0.65x); cost is even (0.95x). Claude turns each PDF page into an image plus text: 2.7x the input tokens, 2.4x the cost, and the long invoice ran out of output tokens.
3. **The cheapest combination was Haiku 5.5 on the docfunnel route**, about 5x cheaper per document than Gemini 3.5 Flash-Lite: input prices are close, but Gemini's output costs US$ 2.50 per 1M tokens against Haiku's US$ 0.50, and output dominates.
4. **CPU OCR loses to the model reading the scan.** On Gemini, line-item F1 was 100% native against 89% via RapidOCR text; the misses are on scanned pages.

### Open questions for the next runs

- How does each route scale with page count (the 10 large documents, 8 to 10 pages)?
- Does thinking pay for itself? Compare thinking levels / effort on the same documents.
- Does native structured output change accuracy or cost against prompt-only JSON?
- How many output tokens are thinking, and how much would a compact line-item format save?
- A **hybrid route**: text for digital pages, the page image only for pages routed to OCR. Could keep the parse stage's savings and the model's accuracy on scans.
