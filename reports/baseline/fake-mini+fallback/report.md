# Evaluation report: fake-mini + fake-pro fallback

- Targets: `fake:fake-mini`, `fake:fake-pro`
- Dataset: `data/synthetic/receipts.jsonl` (sha256 `c1bd9fbe966e`)
- Prompt version: `v1` - package `0.1.0`
- Created: 2026-11-03T17:28:19+00:00

## Summary

| Metric | Value |
| --- | --- |
| Documents | 60 |
| Field accuracy (micro, 9 header fields) | 98.1% |
| Document exact match | 90.0% |
| Schema compliance (final) | 100.0% |
| Schema compliance (first attempt) | 83.3% |
| Hallucination rate (null fields filled) | 1.7% |
| Line items F1 | 100.0% |
| Review flag rate | 15.0% |
| Review precision / recall | 100.0% / 69.2% |
| Docs needing a retry / fallback | 16.7% / 1.7% |
| Tokens (input / output) | 64,109 / 8,889 |
| Total cost / per doc | $0.000000 / $0.000000 |
| Latency p50 / p95 | 0.2 ms / 0.3 ms |

## Per-field results

| Field | Accuracy | Correct | True null | Incorrect | Missed | Hallucinated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `vendor_name` | 100.0% | 60 | 0 | 0 | 0 | 0 |
| `vendor_tax_id` | 98.3% | 38 | 21 | 0 | 1 | 0 |
| `document_number` | 98.3% | 39 | 20 | 0 | 1 | 0 |
| `date` | 98.3% | 59 | 0 | 0 | 1 | 0 |
| `currency` | 100.0% | 60 | 0 | 0 | 0 | 0 |
| `subtotal` | 95.0% | 38 | 19 | 0 | 3 | 0 |
| `tax` | 98.3% | 37 | 22 | 0 | 0 | 1 |
| `total` | 98.3% | 59 | 0 | 1 | 0 | 0 |
| `payment_method` | 96.7% | 27 | 31 | 0 | 1 | 1 |

## By layout

| Value | Docs | Field accuracy | Exact match |
| --- | ---: | ---: | ---: |
| invoice | 19 | 97.7% | 89.5% |
| minimal | 11 | 99.0% | 90.9% |
| pos | 30 | 98.1% | 90.0% |

## By locale

| Value | Docs | Field accuracy | Exact match |
| --- | ---: | ---: | ---: |
| br | 17 | 98.7% | 94.1% |
| de | 14 | 97.6% | 85.7% |
| uk | 12 | 97.2% | 83.3% |
| us | 17 | 98.7% | 94.1% |

## By variant

| Value | Docs | Field accuracy | Exact match |
| --- | ---: | ---: | ---: |
| clean | 45 | 99.8% | 97.8% |
| misprinted | 7 | 100.0% | 100.0% |
| ocr_noise | 8 | 87.5% | 37.5% |

## Documents with errors

| Document | Wrong fields | Line items (fp/fn) | Flagged for review | Reasons |
| --- | --- | --- | --- | --- |
| doc-008 | tax (hallucinated) | 0/0 | **no** | - |
| doc-013 | vendor_tax_id (missed) | 0/0 | **no** | - |
| doc-029 | document_number (missed), subtotal (missed) | 0/0 | **no** | - |
| doc-031 | subtotal (missed), payment_method (hallucinated) | 0/0 | **no** | - |
| doc-040 | date (missed), total (incorrect) | 0/0 | yes | missing_required_field:date, line_items_total_mismatch:line_items,total |
| doc-057 | subtotal (missed), payment_method (missed) | 0/0 | yes | low_confidence:total |
