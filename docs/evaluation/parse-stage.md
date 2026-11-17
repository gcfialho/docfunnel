# Evaluation: parse stage

How well does the parse stage turn PDFs and scans into text, and how fast? Code: [`src/docfunnel/evals/parse/`](../../src/docfunnel/evals/parse/). Full baseline report: [`reports/baseline/parse/report.md`](../../reports/baseline/parse/report.md).

```bash
uv run docfunnel generate-pdfs                                   # 50 PDFs + manifest.jsonl
uv run docfunnel eval-parse --ocr-engine rapidocr --ocr-engine tesseract
uv run docfunnel compare-parse reports/baseline/parse/report.json reports/parse-latest/report.json
```

## Dataset

`docfunnel generate-pdfs` (seed 11) writes 50 PDFs with 134 pages and a `manifest.jsonl` with the ground truth. The PDFs are not committed; CI regenerates them, and the eval checks the manifest hash against the baseline.

| Dimension | Values |
| --- | --- |
| Document types | multi-page invoice (line items across pages, repeated table header, totals on the last page, optional terms), contract (parties, clauses with term, fee, notice period, liability cap and governing law, a schedule, signatures) |
| Locales | US (Letter), UK, DE, BR (A4); the currency, number and date formats of the receipt dataset |
| Variants | digital, scanned light (200 dpi, up to 0.8° rotation, light blur and noise, JPEG q70), scanned heavy (150 dpi, up to 2° rotation, lower contrast, more noise, speckle, JPEG q35), mixed (one scanned page in a digital PDF) |
| Pages | 78 digital, 30 scanned light, 26 scanned heavy; 1 to 4 pages per document |
| Hard cases | digital pages printed over a full-page letterhead image; scans with a digital scanner stamp (`ocr:scan_with_stray_text`) |
| Ground truth | reference text of every page, scanned/digital label, and for each field its value, gold page, printed quote and character span |

## Metrics

| Metric | Definition |
| --- | --- |
| OCR routing precision / recall | Over pages: "routed to OCR" against "page is a scanned image". |
| CER / WER | Levenshtein distance over characters / words divided by the reference length, after collapsing whitespace. Micro-averaged over pages. |
| Field recall | Share of labelled fields whose printed value (whitespace ignored) appears in the parsed text of its gold page: an upper bound on what the LLM step can extract. |
| Throughput | Pages per second. Text extraction is measured in one process (best of 3). The pipeline is measured in the page pool after warm-up, with cold start, per-page OCR latency inside a worker and peak worker memory reported separately. |

## Results

Command: `uv run docfunnel eval-parse --ocr-engine rapidocr --ocr-engine tesseract --out reports/baseline/parse`. Hardware: Apple M4 Pro (12 cores), 24 GB RAM, macOS (Darwin 25.6, arm64), Python 3.12.12; pypdfium2 5.14.0, RapidOCR 3.10.0 with ONNX Runtime 1.31.1, Tesseract 5.5.3 with the `eng` model; 12 worker processes, OCR at 200 dpi.

OCR routing: accuracy 99.3%, precision 98.2%, recall 100.0%. All 56 scanned pages went to OCR. The one false positive is a short last page of a digital invoice printed over a full-page letterhead image, which the "scan with stray text" rule takes for a scan. It costs one unnecessary OCR call; it does not lose text.

| Pages | Engine | CER | WER | Field recall |
| --- | --- | ---: | ---: | ---: |
| digital (78) | text layer | 0.0% | 0.0% | 100.0% |
| scanned light (30) | RapidOCR | 1.6% | 1.9% | 100.0% |
| scanned heavy (26) | RapidOCR | 5.5% | 18.9% | 73.7% |
| scanned light (30) | Tesseract | 6.0% | 14.3% | 90.7% |
| scanned heavy (26) | Tesseract | 37.3% | 75.2% | 27.4% |

| Throughput | Result |
| --- | ---: |
| Text extraction, 1 process: pypdfium2 / pypdf (the previous loader) | 1,745 / 252 pages/s (6.9x) |
| pypdfium2 with OCR decision and line blocks with boxes, 1 process | 905 pages/s |
| Full set, 12 workers, RapidOCR: all pages / OCR pages | 3.05 / 1.3 pages/s |
| Full set, 12 workers, Tesseract: all pages / OCR pages | 25.2 / 10.7 pages/s |
| OCR latency per page inside a worker, p50: RapidOCR / Tesseract | 9.2 / 0.97 s |
| Cold start: spawn 12 workers and load RapidOCR in each | 0.75 s |
| Peak memory of one RapidOCR worker | 1.86 GB |
| Full set, RapidOCR, 1 process x 12 threads (`--workers 1 --ocr-threads 12`) | 1.03 pages/s |

## What this shows

- **Digital pages need no OCR, and the text layer is exact.** CER is 0.0% on all 78 digital pages, and every field printed on them is found.
- **RapidOCR is more accurate, Tesseract is faster.** On heavy scans RapidOCR keeps CER at 5.5% where Tesseract reaches 37.3%, and finds 73.7% of the printed field values against 27.4%. Tesseract is about 8x faster on this machine. The `eng` Tesseract model also reads `ä` as `a` and `ã` as `a`, which counts as errors on DE and BR documents.
- **Heavy scans lose field values even when CER looks low.** WER on heavy scans (18.9%) is much higher than CER (5.5%): a single wrong character breaks a word, and amounts and IDs are single words. A quarter of the field values on heavy scans are not recoverable as printed; this is the slice where a better OCR model or a GPU would pay off.
- **pypdfium2 is 6.9x faster than pypdf on these PDFs**, not the ~30x reported by the py-pdf benchmark. The generated PDFs are simple (standard fonts, no compressed object streams), which favours pypdf. Either way, text extraction is not the bottleneck: OCR is, at 1 to 11 pages/s against hundreds.
- **Rendering at 150 instead of 200 dpi** (`--dpi 150`) gave 1.5 instead of 1.3 OCR pages/s with RapidOCR, with CER 1.3% (light) and 6.9% (heavy). 200 dpi stays the default because heavy scans are where errors matter.

## Across platforms

OCR output is not bit-identical across CPUs, so the gate has tolerances (1 pp scanned CER, 2 pp field recall) rather than exact matches. Same generated set, RapidOCR only:

| Run | Routing (acc / prec / rec) | CER light / heavy | Field recall (all) | pypdfium2 vs pypdf |
| --- | --- | ---: | ---: | ---: |
| Baseline: Apple M4 Pro, macOS arm64, 12 workers | 99.3% / 98.2% / 100.0% | 1.6% / 5.5% | 94.2% | 6.9x |
| Linux arm64 container (`python:3.12-slim`), 4 workers | same | 1.7% / 4.5% | 95.1% | n/a |
| GitHub Actions `ubuntu-latest`: Intel Xeon 8370C, x86_64, 4 workers ([CI run, 2026-11-03](https://github.com/gcfialho/docfunnel/actions/runs/41730496056)) | same | 1.8% / 4.3% | 95.1% | 8.5x |

## The gate

`docfunnel compare-parse` gates quality only: routing accuracy, precision and recall may not drop; digital CER may rise by at most 0.1 pp and scanned CER by 1 pp; field recall may drop by at most 2 pp. Absolute throughput is reported but not gated, because shared CI runners are too noisy for timings. The one timing check is relative and runs within the same job: pypdfium2 must stay at least 3x faster than pypdf on the same pages. Engines missing from the candidate run (Tesseract in CI) are reported as skipped.
