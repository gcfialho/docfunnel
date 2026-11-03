# Parse evaluation report: rapidocr+tesseract (M4 Pro, 12 workers)

- Dataset: `data/synthetic/pdf` (manifest sha256 `930684d54d91`): 50 documents, 134 pages (26 heavy, 30 light scanned)
- Hardware: Apple M4 Pro, 12 logical cores, 24.0 GB RAM, Darwin 25.6.0 (arm64), Python 3.12.12
- Versions: pypdfium2 5.14.0, rapidocr 3.10.0, onnxruntime 1.31.1, pytesseract 0.3.13, pypdf 6.21.4, reportlab 5.1.0, tesseract 5.5.3
- Page pool: 12 worker processes x 1 OCR thread(s); OCR render at 200 dpi
- Package `0.1.0`, created 2026-11-03T19:47:13+00:00

## Summary

| Metric | Value |
| --- | --- |
| Documents / pages | 50 / 134 |
| OCR routing accuracy / precision / recall | 99.3% / 98.2% / 100.0% |
| Raw text extraction, 1 process: pypdfium2 / pypdf | 1,745.1 pages/s / 252.1 pages/s (6.9x) |
| [rapidocr] CER digital / scanned light / heavy | 0.0% / 1.6% / 5.5% |
| [rapidocr] WER scanned light / heavy | 1.9% / 18.9% |
| [rapidocr] field recall digital / scanned light / heavy | 100.0% / 100.0% / 73.7% |
| [rapidocr] pipeline, 12 workers: all pages / OCR pages | 3.0 pages/s / 1.3 pages/s |
| [tesseract] CER digital / scanned light / heavy | 0.0% / 6.0% / 37.3% |
| [tesseract] WER scanned light / heavy | 14.3% / 75.2% |
| [tesseract] field recall digital / scanned light / heavy | 99.6% / 90.7% / 27.4% |
| [tesseract] pipeline, 12 workers: all pages / OCR pages | 25.2 pages/s / 10.7 pages/s |

## OCR routing

Label: the page is a scanned image. Prediction: the route starts with `ocr:`.

| | Labelled scanned | Labelled digital |
| --- | ---: | ---: |
| Routed to OCR | 56 | 1 |
| Kept text layer | 0 | 77 |

| Route | Pages |
| --- | ---: |
| `ocr:no_text` | 34 |
| `ocr:scan_with_stray_text` | 23 |
| `text_layer` | 77 |

Misrouted pages:

| Page | Kind | Full-page image | Route |
| --- | --- | --- | --- |
| pdf-004 p3 | digital | yes | `ocr:scan_with_stray_text` |

## Text quality (CER / WER after whitespace normalization)

| Engine | Pages | Kind | CER | WER |
| --- | ---: | --- | ---: | ---: |
| rapidocr | 78 | digital | 0.0% | 0.0% |
| rapidocr | 56 | scanned | 3.5% | 10.0% |
| rapidocr | 26 | scanned_heavy | 5.5% | 18.9% |
| rapidocr | 30 | scanned_light | 1.6% | 1.9% |
| tesseract | 78 | digital | 0.0% | 0.0% |
| tesseract | 56 | scanned | 21.4% | 43.4% |
| tesseract | 26 | scanned_heavy | 37.3% | 75.2% |
| tesseract | 30 | scanned_light | 6.0% | 14.3% |

## Field recall (printed value found on its gold page)

| Engine | Gold page kind | Fields | Found | Recall |
| --- | --- | ---: | ---: | ---: |
| rapidocr | all | 429 | 404 | 94.2% |
| rapidocr | digital | 248 | 248 | 100.0% |
| rapidocr | scanned_heavy | 95 | 70 | 73.7% |
| rapidocr | scanned_light | 86 | 86 | 100.0% |
| tesseract | all | 429 | 351 | 81.8% |
| tesseract | digital | 248 | 247 | 99.6% |
| tesseract | scanned_heavy | 95 | 26 | 27.4% |
| tesseract | scanned_light | 86 | 78 | 90.7% |

## Throughput

Text layer, single process, 78 digital pages, best of 3:

| Extractor | Pages/s |
| --- | ---: |
| pypdfium2: text + OCR decision + line blocks with boxes | 905.2 |
| pypdfium2: raw text only | 1,745.1 |
| pypdf `extract_text()` (previous loader) | 252.1  |

Full pipeline in the page pool (12 processes x 1 thread(s)):

| Engine | Pages/s (all) | OCR pages | OCR pages/s | OCR ms/page p50 / p95 (in a worker) | Cold start | Peak worker RSS | Page errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rapidocr | 3.05 | 57 | 1.3  | 9158.9 / 13478.8 | 0.752 s | 1862.1 MB | 0 |
| tesseract | 25.22 | 57 | 10.7  | 969.2 / 1557.2 | 0.496 s | 1862.1 MB | 0 |

OCR pages/s divides the OCR pages by the wall time of the whole run (text-layer pages
included), so it slightly understates OCR speed. Peak worker RSS is the largest
resident set of any worker process so far in this run.

## Worst pages: rapidocr

| Page | Kind | Route | CER | WER |
| --- | --- | --- | ---: | ---: |
| pdf-028 p2 | scanned_light | `ocr:no_text` | 13.3% | 16.2% |
| pdf-005 p1 | scanned_heavy | `ocr:no_text` | 12.3% | 51.2% |
| pdf-027 p3 | scanned_light | `ocr:scan_with_stray_text` | 10.3% | 14.0% |
| pdf-010 p2 | scanned_heavy | `ocr:scan_with_stray_text` | 9.6% | 20.1% |
| pdf-017 p1 | scanned_heavy | `ocr:no_text` | 9.3% | 13.3% |
| pdf-008 p2 | scanned_light | `ocr:scan_with_stray_text` | 8.6% | 10.7% |
| pdf-014 p1 | scanned_heavy | `ocr:scan_with_stray_text` | 8.3% | 14.5% |
| pdf-035 p1 | scanned_heavy | `ocr:no_text` | 8.0% | 17.2% |

## Worst pages: tesseract

| Page | Kind | Route | CER | WER |
| --- | --- | --- | ---: | ---: |
| pdf-010 p2 | scanned_heavy | `ocr:scan_with_stray_text` | 79.5% | 88.1% |
| pdf-001 p3 | scanned_heavy | `ocr:no_text` | 67.1% | 107.3% |
| pdf-005 p1 | scanned_heavy | `ocr:no_text` | 55.2% | 114.0% |
| pdf-030 p1 | scanned_heavy | `ocr:scan_with_stray_text` | 50.9% | 92.5% |
| pdf-012 p1 | scanned_heavy | `ocr:scan_with_stray_text` | 46.5% | 75.6% |
| pdf-011 p3 | scanned_heavy | `ocr:scan_with_stray_text` | 45.3% | 80.2% |
| pdf-017 p1 | scanned_heavy | `ocr:no_text` | 43.3% | 74.8% |
| pdf-048 p1 | scanned_heavy | `ocr:no_text` | 41.9% | 77.8% |
