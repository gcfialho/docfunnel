# Evaluation report: fake-mini (no fallback)

- Targets: `fake:fake-mini`
- Dataset: `data/synthetic/receipts.jsonl` (sha256 `c1bd9fbe966e`)
- Prompt version: `v1` - package `0.1.0`
- Created: 2026-11-03T17:28:20+00:00

## Summary

| Metric | Value |
| --- | --- |
| Documents | 60 |
| Field accuracy (micro, 9 header fields) | 96.7% |
| Document exact match | 88.3% |
| Schema compliance (final) | 98.3% |
| Schema compliance (first attempt) | 83.3% |
| Hallucination rate (null fields filled) | 1.7% |
| Line items F1 | 98.0% |
| Review flag rate | 16.7% |
| Review precision / recall | 100.0% / 71.4% |
| Docs needing a retry / fallback | 16.7% / 0.0% |
| Tokens (input / output) | 63,199 / 8,688 |
| Total cost / per doc | $0.000000 / $0.000000 |
| Latency p50 / p95 | 0.2 ms / 0.3 ms |

## Per-field results

| Field | Accuracy | Correct | True null | Incorrect | Missed | Hallucinated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `vendor_name` | 98.3% | 59 | 0 | 0 | 1 | 0 |
| `vendor_tax_id` | 96.7% | 37 | 21 | 0 | 2 | 0 |
| `document_number` | 96.7% | 38 | 20 | 0 | 2 | 0 |
| `date` | 96.7% | 58 | 0 | 0 | 2 | 0 |
| `currency` | 98.3% | 59 | 0 | 0 | 1 | 0 |
| `subtotal` | 93.3% | 37 | 19 | 0 | 4 | 0 |
| `tax` | 96.7% | 36 | 22 | 0 | 1 | 1 |
| `total` | 96.7% | 58 | 0 | 1 | 1 | 0 |
| `payment_method` | 96.7% | 27 | 31 | 0 | 1 | 1 |

## By layout

| Value | Docs | Field accuracy | Exact match |
| --- | ---: | ---: | ---: |
| invoice | 19 | 97.7% | 89.5% |
| minimal | 11 | 99.0% | 90.9% |
| pos | 30 | 95.2% | 86.7% |

## By locale

| Value | Docs | Field accuracy | Exact match |
| --- | ---: | ---: | ---: |
| br | 17 | 98.7% | 94.1% |
| de | 14 | 91.3% | 78.6% |
| uk | 12 | 97.2% | 83.3% |
| us | 17 | 98.7% | 94.1% |

## By variant

| Value | Docs | Field accuracy | Exact match |
| --- | ---: | ---: | ---: |
| clean | 45 | 97.8% | 95.6% |
| misprinted | 7 | 100.0% | 100.0% |
| ocr_noise | 8 | 87.5% | 37.5% |

## Documents with errors

| Document | Wrong fields | Line items (fp/fn) | Flagged for review | Reasons |
| --- | --- | --- | --- | --- |
| doc-008 | tax (hallucinated) | 0/0 | **no** | - |
| doc-013 | vendor_tax_id (missed) | 0/0 | **no** | - |
| doc-019 | vendor_name (missed), vendor_tax_id (missed), document_number (missed), date (missed), currency (missed), subtotal (missed), tax (missed), total (missed) | 0/5 | yes | extraction_failed |
| doc-029 | document_number (missed), subtotal (missed) | 0/0 | **no** | - |
| doc-031 | subtotal (missed), payment_method (hallucinated) | 0/0 | **no** | - |
| doc-040 | date (missed), total (incorrect) | 0/0 | yes | missing_required_field:date, line_items_total_mismatch:line_items,total |
| doc-057 | subtotal (missed), payment_method (missed) | 0/0 | yes | low_confidence:total |
