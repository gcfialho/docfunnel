# Limitations and next experiments

docfunnel is a proof of concept. It tests one idea: parse a PDF on the CPU before an LLM reads it. The results and verdicts are in the [proof-of-concept report](evaluation/real-models.md). This page lists what the evidence does not cover, what the code does not do yet, and the experiments that would settle the open questions, cheapest first.

## Limits of the evidence

- **Synthetic documents only.** The 39 invoices, their scans and the noise on them come from the repo's own generator. Real phone photos, thermal receipts, stamps, handwriting and fax artefacts are not covered.
- **In-sample results.** The `hybrid-ocr` route and prompt v2 were designed after reading errors on the same invoices they were scored on. The `hybrid-ocr` repeat used 29 of those invoices, so it measures run-to-run noise, not overfitting.
- **Small samples, mostly single runs.** On 39 documents a single exact-match rate is uncertain by 10 to 15 points. Runs of the same setup changed the outcome of up to 7 of 39 invoices.
- **Few models per route.** `hybrid-ocr` has run on GPT-6 Luna (39 invoices) and a local Gemma 4 12B (12) only. The Anthropic and Gemini keys stopped working before it existed: one was revoked, the other ran out of credit.
- **List-price costs.** Costs are token counts times the [price table](../src/docfunnel/extract/pricing.json), not provider bills.

## Limits of the code

- **The business rules miss consistent errors.** They catch missing line items, totals that do not add up and implausible dates. They do not catch a misread identifier or a row dropped with the totals still matching, and those were most of the errors in the runs.
- **Citations are not used yet.** Blocks carry page numbers, spans and boxes, but the model is not asked to cite them, and its answers are not checked against them.
- **Lines, not layout.** Blocks are text lines. Tables, paragraphs and multi-column reading order would need a layout model.
- **No `garbled` test pages.** The rule for broken text layers (fonts without a Unicode map) exists and is unit-tested, but the generator does not produce such PDFs.
- **Tesseract runs with the `eng` model only**, which costs it accuracy on German and Portuguese. `ParseOptions(tesseract_lang="eng+deu+por")` works when those models are installed.
- **The `text` route stays the default.** It works with every provider, including those that cannot read images. `hybrid-ocr` stays opt-in until the experiments below confirm it.
- **The bundled receipt dataset is read from the working directory.** `docfunnel eval` defaults to `data/synthetic/receipts.jsonl`, so run it from the repository root, or pass `--dataset`.

## Next experiments

In order of cost. Each one answers a question the current evidence leaves open.

1. **Out-of-sample check of `hybrid-ocr`.** Generate a fresh invoice set with another seed. Run GPT-6 Luna on `text`, `native` and `hybrid-ocr`, three times each. About US$ 0.30.
2. **Real scans.** A CORD v2 receipt subset on the same routes.
3. **More models on `hybrid-ocr`:** Claude Haiku 5.5 and Gemini 3.5 Flash-Lite, about US$ 0.20 with working keys.
4. **Rules that check answers against evidence.** For example, flag an identifier that appears in neither the text layer nor the OCR text. Then measure again how many wrong answers go unflagged (the *Wrong, not flagged* column in [`reports/e2e/`](../reports/e2e/README.md)).

## Beyond this proof of concept

These ideas only matter if the experiments above hold up:

- **More document types**, with a cheap classifier in front: rules, then TF-IDF, then embeddings, then an LLM only when unsure.
- **Answers with verified citations.** The model quotes its evidence inside the schema, and code checks each quote.
- **A GPU comparison.** GPU OCR and layout models (Docling, PaddleOCR-VL, olmOCR-2) on the same pages, to see which pages justify a GPU.
