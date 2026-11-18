# Proof of concept: what should an LLM read from a PDF?

docfunnel started from one idea and was built to test it. This page states the idea, how it was tested, what held up and what did not, and what would still have to be done to trust the result. It is a proof of concept on 39 synthetic invoices, mostly one run per setup, and about US$ 6.50 of API calls. It is not a product benchmark.

## The idea, and the hypotheses

**Starting idea (H1).** Read each PDF on the CPU first: the text layer where the page has one, OCR where it is scanned. Then send the text to a small model. This should cost less than sending the PDF to the model, at the same accuracy.

Two more hypotheses came up while testing it:

- **H2, formed after looking at the errors of H1.** On scanned pages, send the model the page image *and* its OCR text (the `hybrid-ocr` route). Text pages still go as text.
- **H3.** Business rules (totals that add up, line items present, plausible dates) catch the wrong answers, so a cheaper input is safe because errors go to a person.

## How it was tested

- **Documents.** 39 invoices made by the repo's own seeded generator, 174 pages in all.
  - 29 small (1 to 4 pages, 17 to 170 line items) and 10 large (an invoice with contracts annexed, 8 to 10 pages).
  - 10 are fully digital. 29 have at least one scanned page, rendered and degraded by a script.
  - The labels are right by construction.
- **Score.** Exact match: every header field and every line item right. Header fields are vendor, tax ID, number, date, currency, subtotal, tax, total and payment method.
- **Held fixed.** The prompt, the JSON Schema output, one repair turn, the scoring, and the price table used for cost (token counts times list prices).
- **Routes.** These are what the model reads:

  | Route (`route=`) | What the model reads |
  | --- | --- |
  | `text` | the parse stage's text: the text layer, and OCR text on scanned pages |
  | `native` | the PDF file |
  | `hybrid` | text pages as text, and an image of each scanned page in its place |
  | `hybrid-ocr` | `hybrid`, plus each scanned page's OCR text after its image |

- **Statistics.**
  - Each exact-match rate has a 95% Wilson interval. On 39 documents, that interval spans 10 to 15 points on each side.
  - Two routes of one model are compared on the same documents with an exact McNemar test.
  - Only the documents one route got right and the other got wrong count in that test.
  - Every figure on this page is generated from the reports in [`reports/e2e/`](../../reports/e2e/README.md) by `docfunnel e2e-summary`, and a test fails if they drift.

## Results

![Exact match against cost per 1,000 invoices, with 95% intervals, by what the model reads](../img/e2e-accuracy-vs-cost.svg)

All 39 invoices, one run each. *Wrong, not flagged* counts the documents with an error that the business rules did not send to review.

| Model | Route | Exact match | 95% interval | Wrong, not flagged | Cost per 1k invoices |
| --- | --- | ---: | ---: | ---: | ---: |
| GPT-6 Luna | hybrid-ocr | 100% (39/39) | 91 to 100% | 0 of 0 | $2.15 |
| GPT-6 Luna | native | 85% | 70 to 93% | 5 of 6 | $1.71 |
| GPT-6 Luna | hybrid | 80% | 64 to 89% | 5 of 8 | $1.85 |
| GPT-6 Luna | text | 72% | 56 to 83% | 6 of 11 | $1.47 |
| Gemini 3.5 Flash-Lite | native | 97% | 87 to 100% | 1 of 1 | $11.86 |
| Gemini 3.5 Flash-Lite | text | 69% | 54 to 81% | 11 of 12 | $12.46 |
| Gemini 3.8 Flash | native | 97% | 87 to 100% | 0 of 1 | $14.40 |
| Gemini 3.8 Flash | text | 64% | 48 to 77% | 12 of 14 | $15.20 |
| Gemini 3.1 Flash-Lite | text | 87% | 73 to 94% | 4 of 5 | $7.39 |
| Gemini 3.1 Flash-Lite | native | 85% | 70 to 93% | 4 of 6 | $7.10 |
| Claude Haiku 5.5 | native | 82% | 67 to 91% | 2 of 7 | $4.29 |
| Claude Haiku 5.5 | text | 69% | 54 to 81% | 1 of 12 | $3.21 |

Smaller runs, each compared only within itself:

| Set | What was run | Result |
| --- | --- | --- |
| 29 invoices with scans, same documents | GPT-6 Luna, hybrid-ocr, repeated | 28 of 29 |
| 29 invoices with scans | Gemini 3.1 Flash-Lite and 3.5 Flash-Lite, hybrid | 97% and 93% |
| 12-invoice sample | Claude Haiku 5.5 at effort `medium`, hybrid | 12 of 12 (interval 76 to 100%) |
| 12-invoice sample | Claude Sonnet 5.5, native or hybrid | 9 of 12, at $52 per 1k |
| 12-invoice sample | Gemma 4 12B on a laptop (Ollama) | hybrid-ocr 8, text 7, hybrid 4 of 12 |

## Verdicts

### H1: parse first, send text. Cheaper at the same accuracy?

**Mostly not supported.**

- **Cost.** It was not cheaper on Gemini or OpenAI. Output tokens were 52 to 92% of the cost, and both read a PDF in about as many input tokens as its text, so cutting input could not save much. On Claude Haiku it was 25% cheaper, because Claude bills a PDF page as text plus an image.
- **Accuracy on digital PDFs.** Text did as well as the PDF: every model got all 10 fully digital invoices right on the text route.
- **Accuracy on scanned pages.** Text did worse. OCR text loses table rows.
  - For Gemini 3.5 Flash-Lite and 3.8 Flash, the PDF beat the text 12 to 1 and 14 to 1 (p = 0.003 and 0.001): they read the scans themselves.
  - For GPT-6 Luna and Claude Haiku the gap pointed the same way but was not significant (p = 0.23 and 0.33).
  - For Gemini 3.1 Flash-Lite there was no gap.

### H2: image and OCR text for scanned pages

**Supported for one model, on the documents it was developed on.**

- **GPT-6 Luna on all 39 invoices.** hybrid-ocr got every invoice right. Against the other routes on the same documents:
  - against the PDF: 6 to 0 (p = 0.031);
  - against text only: 11 to 0 (p = 0.001);
  - against the image only: 8 to 0 (p = 0.008).
  - Repeated on the 29 invoices with scans: 28 of 29.
- **Why it works, from the errors.** OCR text keeps identifiers right and loses table rows. With the image alone, GPT-6 Luna read the rows but misread tax IDs and document numbers. Given both, it used each for what it gets right.
- **Gemma 4 12B on 12 invoices.** 8 of 12 on hybrid-ocr against 7 on text: one document, which proves nothing at that size. The image alone was clearly worse (4 of 12).

**The caveat that matters most.** The route was designed after reading the errors on these 39 invoices, and the repeat used 29 of the same invoices. Until it is run on documents it has not seen, this is a promising in-sample result, not a confirmed one.

### H3: business rules catch the wrong answers

**Not supported as a safety net.**

- **What the rules did catch.** The `line_items_missing` rule flagged every answer that dropped its line items, which was most of Claude Haiku's errors (11 of 12 flagged on text).
- **What they missed.** Most wrong answers were consistent and wrong: a misread identifier, or a row dropped while the totals still matched. No rule sees those.
  - Gemini 3.5 Flash-Lite on text: 11 of 12 wrong answers were not flagged.
  - GPT-6 Luna on the PDF: 5 of 6 were not flagged.
- **What would help.** Checks against evidence, such as a field the OCR text contradicts, or two routes disagreeing. More arithmetic rules would not.

### Other observations

- **A bigger model did not help here.** Gemini 3.8 Flash matched 3.5 Flash-Lite at a higher price. Claude Sonnet 5.5 got 9 of 12 against Haiku's 12 of 12 at effort `medium`, for 12 times the cost. Both comparisons are small.
- **Tuning knobs mostly did nothing measurable.**
  - Reasoning effort `low` on GPT-6 Luna: within the noise, for 12% more.
  - Compact JSON keys: did not shorten the answers.
- **Runs are noisy.** The same GPT-6 Luna text-route setup, run twice, changed the outcome of 7 of 39 invoices.

## What this does not show

- **Real documents.** The scans, and the OCR errors on them, come from our own generator. Real scans have skew, stamps, handwriting and phone photos.
- **Out-of-sample accuracy.** The prompt (v2) and the hybrid-ocr route were both changed after seeing errors on these invoices.
- **Repeatability.** Most setups ran once. GPT-6 Luna's text and hybrid routes ran twice, and hybrid-ocr was repeated on 29 of the same invoices. That measures run-to-run noise, not overfitting.
- **Generality across models.** hybrid-ocr ran on GPT-6 Luna and a local Gemma only. The Anthropic and Gemini keys stopped working before it existed: one was revoked, the other ran out of credit.
- **Real bills.** Costs are token counts times list prices checked between 2026-11-03 and 2026-11-17. The Gemini prepaid credit ran out after US$ 3.81 by our table, below the US$ 5 cap, so the Gemini bill may be higher than shown.

## What would confirm it

In order of cost:

1. **New documents.** Generate a fresh invoice set with another seed and run GPT-6 Luna on text, native and hybrid-ocr, three times each. This tests H2 out of sample. About US$ 0.30.
2. **Real scans.** A CORD v2 receipt subset, same routes.
3. **Other models.** hybrid-ocr on Claude Haiku and Gemini 3.5 Flash-Lite (needs working keys, about US$ 0.20).
4. **A rule that compares answers with evidence.** For example, flag an identifier that does not appear in the OCR or text-layer text. Then measure the *wrong, not flagged* column again.

## Trying the idea

If you want to try it on your own documents, this is what the evidence above suggests. It is not a recommendation backed by out-of-sample tests.

| Documents | `route` | Basis |
| --- | --- | --- |
| Digital PDFs, text | `text` (the default) | Same accuracy as the PDF here; 25% cheaper on Claude |
| Scanned or mixed PDFs, a model that reads images | `hybrid-ocr` | Best in-sample result on GPT-6 Luna; untested on other API models |
| Documents that must stay on your machines | `text` or `hybrid-ocr` on [Ollama](../providers.md) | Close on Gemma 4 12B (7 and 8 of 12); minutes per invoice on a laptop, and line items are weak |
| You would rather not run a parse stage | `native` | Gemini 3.5 Flash-Lite read these PDFs well (97%), at about five times GPT-6 Luna's hybrid-ocr cost |

On a fully digital PDF, `text`, `hybrid` and `hybrid-ocr` send the same text. They differ only on pages the parse stage sends to OCR.

## Reproduce

Everything but the model calls runs offline. GPT-6 Luna on all four routes and 39 invoices costs about $0.30; a Gemini Flash model about $2 at the prices above.

```bash
uv sync --all-extras
uv run docfunnel generate-pdfs && uv run docfunnel generate-e2e     # 39 invoices, seeded

export OPENAI_API_KEY=...
uv run docfunnel eval-e2e -t openai:gpt-6-luna \
  --route text --route native --route hybrid --route hybrid-ocr \
  --budget-usd 1 --out reports/e2e-latest
```

- **Cheaper subsets:** `--sample 12` or `--where scan=has_scanned_pages`.
- **Variants:** `-t provider:model+option=value`, e.g. `anthropic:claude-haiku-5-5+effort=medium`.
- **Spending cap:** `--budget-usd` caps spending per provider. Calls past the cap are skipped and reported, never sent.
- **Failing providers:** one whose calls keep failing without using tokens (no credit, bad key) is stopped after three calls.
- **Publishing a run:** move its folder to `reports/e2e/NN-name/` and run `uv run docfunnel e2e-summary` to regenerate the index, the intervals, the paired tests and the chart.

How each run came about, in order, with its cost: the [lab notebook](findings.md).
