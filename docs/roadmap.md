# Limitations and roadmap

Phase 1 (this version) is the parse stage and its evaluation, feeding the LLM step, which already handles schema validation, repair, fallback, human-review routing and cost tracking.

## Known limitations

- **The parse stage is not yet connected to citations.** Blocks carry page numbers and spans, but the extractor still receives flat text. Using them for evidence comes in phase 3.
- **Synthetic scans are easier than real ones.** The noise is simulated; real phone photos, thermal receipts and fax artefacts are not covered. There is no public, permissively licensed scan set in the repo yet (phase 2 adds CORD v2 and olmOCR-bench subsets).
- **No `garbled` test pages.** The rule for broken text layers (fonts without a Unicode map) exists and is unit-tested, but the generator does not produce such PDFs yet.
- **Lines, not layout.** Blocks are text lines. Paragraphs, tables and multi-column reading order need a layout model (Docling as an optional extra, planned).
- **Tesseract runs with the `eng` model only**, which costs it accuracy on German and Portuguese text; `ParseOptions(tesseract_lang="eng+deu+por")` is available when those models are installed.
- **The LLM step is still evaluated only with the fake provider.** No real-model numbers are published, and no request has been sent to the OpenAI, Anthropic or Gemini APIs yet. The adapters follow the providers' current documentation and the installed SDKs (see [Providers, models and pricing](providers.md)), but the first real call per provider is still the real test.
- **The bundled receipt dataset is read from the working directory.** `docfunnel eval` defaults to `data/synthetic/receipts.jsonl`, so run it from the repository root (or pass `--dataset`).

## Next phases

- **Phase 2: classify and retrieve.** More document types in the generator (bank statements, NDAs, purchase orders, letters and hard negatives); a cascade classifier (rules, then TF-IDF with logistic regression, then static embeddings, then the LLM only when confidence is low) with macro-F1 and risk-coverage curves; layout-aware chunking; BM25, dense and hybrid retrieval (RRF) with recall@k; a local benchmark on CORD v2 and olmOCR-bench subsets.
- **Phase 3: LLM modes and the experiment matrix.** Free-form QA, fixed question sets per document type and structured extraction behind one `Task` interface; a schema per document type (native structured output for OpenAI, Anthropic and Gemini is already in place for the receipt schema); evidence inside the schema (`chunk_id` + quote) checked in code, with grounded-answer rate and page-citation accuracy; an end-to-end matrix recorded in cassettes, a quality-vs-cost Pareto chart and per-stage cost and latency.
- **Phase 4 (optional): GPU benchmark.** A single, reproducible run of GPU OCR and layout models (Docling, PaddleOCR-VL, olmOCR-2) on the same pages, with price and date recorded, to find which pages (likely the heavy scans) justify a GPU route.
