# Findings from real-model runs

A lab notebook: what each run with a real model showed, what it cost, and what changed in the code because of it. Newest entries first. Raw reports are in [`reports/e2e/`](../../reports/e2e/).

Spend so far (cap: US$ 5 per provider key): Gemini ~US$ 3.81 by our price table, after which the key's prepaid credit ran out; Anthropic ~US$ 0.66.

## 2026-11-17: compact line items; the Gemini key runs out of credit

**Setup.** Hybrid route on all 39 invoices with `--compact-output` (one-letter line-item keys), Gemini 3.1 Flash-Lite and Claude Haiku 5.5, compared with the standard answer format on the same documents (hybrid on the 29 with scans, docfunnel on the 10 digital ones). Cost: Anthropic US$ 0.14. Report: [`reports/e2e-compact/`](../../reports/e2e-compact/report.md).

| `claude-haiku-5-5` | Exact match | Line items F1 | Output tok/doc | Cost per 1k docs |
| --- | ---: | ---: | ---: | ---: |
| standard keys | 82.1% | 94.3% | 5,216 | $3.60 |
| compact keys | 89.7% | 98.1% | 5,274 | $3.63 |

1. **Compact keys did not shorten the answer.** Output tokens were unchanged on average and 8% lower (median) on invoices with more than 20 items. Key names such as `"description"` are about one token each; the values (descriptions, numbers) are the output. The accuracy difference is within the run-to-run noise seen above. The option stays, off by default.
2. **The Gemini key ran out of prepaid credit** (HTTP 402) after ~US$ 3.81 of calls by our price table, below the US$ 5 cap. Either the prepaid balance was lower than the cap, or the bill is higher than our table says. Check the AI Studio billing page before trusting the Gemini cost figures above to the cent.
3. **The eval scored the 402s as 39 failed extractions.** It now stops a provider after 3 consecutive calls that fail without using a token and reports why (`unavailable` in the report). The Gemini rows were removed from this report.

## 2026-11-17: hybrid route, images in place

**Setup.** Same 29 invoices with scanned pages and the same three models; each scanned page's image now sits between the text of the pages around it. Cost: Gemini US$ 0.53, Anthropic US$ 0.10. Report: [`reports/e2e-hybrid/`](../../reports/e2e-hybrid/report.md).

| Model | Route | Exact match | Line items F1 | Cost per 1k docs |
| --- | --- | ---: | ---: | ---: |
| `gemini-3.1-flash-lite` | docfunnel | 82.8% | 98.7% | $7.08 |
| `gemini-3.1-flash-lite` | native | 79.3% | 97.7% | $6.76 |
| `gemini-3.1-flash-lite` | **hybrid** | **96.6%** | **100.0%** | **$6.99** |
| `gemini-3.5-flash-lite` | docfunnel | 58.6% | 96.1% | $11.68 |
| `gemini-3.5-flash-lite` | native | **100.0%** | 100.0% | $10.93 |
| `gemini-3.5-flash-lite` | hybrid | 93.1% | 100.0% | $11.43 |
| `claude-haiku-5-5` | docfunnel | 58.6% | 89.1% | $3.08 |
| `claude-haiku-5-5` | native | **86.2%** | 92.4% | $4.12 |
| `claude-haiku-5-5` | hybrid | 75.9% | 91.6% | $3.60 |

1. **Placement was the whole problem.** Gemini 3.5 Flash-Lite went from 75.9% (images first) to 93.1% exact match, 3.1 Flash-Lite from 55.2% to 96.6%.
2. **The hybrid route makes the cheapest Gemini model match the best one.** Over all 39 invoices (hybrid on the 29 with scans, the identical docfunnel request on the 10 digital ones), Gemini 3.1 Flash-Lite reaches ~97.4% exact match at ~US$ 7.32 per 1k documents; Gemini 3.5 Flash-Lite on native PDFs reaches 97.4% at US$ 11.86. Same accuracy, 62% of the cost.
3. **It is not a rule.** On Gemini 3.5 Flash-Lite and Haiku 5.5 native input is still the most accurate route; the hybrid route sits between docfunnel and native in both accuracy and cost.
4. **Run-to-run variance is large at this size.** Haiku's hybrid exact match was 79.3% in the first run and 75.9% in this one, with the same requests for most documents; on the 10 large documents it moved from 80% to 60%. Differences under ~10 pp on 29 documents, or ~20 pp on 10, are within noise.

## 2026-11-17: hybrid route, first attempt (images before the text)

**Setup.** `--route hybrid --where scan=has_scanned_pages`: the 29 invoices with scanned pages; Gemini 3.5 / 3.1 Flash-Lite and Claude Haiku 5.5. Every page the parse stage routed to OCR was sent as a 150 dpi JPEG, all images before the text, with a note in the text where each scanned page was ("read it from attached image 2"). Cost: Gemini US$ 0.44, Anthropic US$ 0.10. Report: [`reports/e2e-hybrid-v1-images-first/`](../../reports/e2e-hybrid-v1-images-first/report.md).

| Model | docfunnel exact match | native | hybrid v1 | hybrid v1 cost / native cost |
| --- | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | 58.6% | 100.0% | 75.9% | 0.84x |
| `claude-haiku-5-5` | 58.6% | 86.2% | 79.3% | 0.87x |
| `gemini-3.1-flash-lite` | 82.8% | 79.3% | 55.2% | 0.87x |

1. **Gemini ignored images it could not place.** Every Gemini miss had items missing (never extra) from the scanned pages, and output fell from ~4,000 to 200 to 900 tokens. On two large documents whose invoice page was the scan, all header fields were wrong. With minimal thinking, the model did not connect "read it from attached image 2" to the second image.
2. **Haiku used the images.** Exact match rose from 59% to 79%, at 13% less than native.
3. **Fix:** the adapters now put each file where its `[[attachment:N]]` marker is, so the model reads page 1 text, page 2 image, page 3 text. On the two worst documents both extractions became correct (US$ 0.01 check).
4. **Gemini 3.5 Flash-Lite at `minimal` thinking spends no thinking tokens** (`thoughts_token_count` is 0): all of its output is the JSON answer, so a shorter answer is its only output-cost lever.

**Also found:** the first hybrid run aborted (SIGABRT, no log) because page images were rendered with PDFium inside the model-call thread pool, and PDFium is not thread-safe. Images are now rendered once per document before the threads start; a test runs the hybrid route with 4 workers. Spend before the crash was not recorded; it is counted as up to US$ 0.05 above.

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
