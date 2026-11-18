# End-to-end evaluation: GPT-6 Luna, effort none and low, all 39 invoices

- Dataset: `data/synthetic/e2e`: 39 invoices, 174 pages
- Models: `openai:gpt-6-luna`, `openai:gpt-6-luna+reasoning_effort=low`; routes: text, native, hybrid
- Spend: openai $0.40 of $1.50; skipped calls (budget reached or provider stopped): 0
- Package `0.1.0`, prompt `v2`, created 2026-11-17T22:17:26+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | text | 39 | 100.0% | 74.4% | 95.7% | 100.0% | 3,933 | 2,582 | 0 | $0.00168 | $1.68 | 16.3 s | 16.1 s |
| `gpt-6-luna` | native | 39 | 98.0% | 84.6% | 98.7% | 100.0% | 5,232 | 2,375 | 0 | $0.00171 | $1.71 | 16.1 s | n/a |
| `gpt-6-luna` | hybrid | 39 | 97.7% | 84.6% | 99.8% | 100.0% | 7,264 | 2,480 | 0 | $0.00197 | $1.97 | 15.8 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | text | 39 | 100.0% | 71.8% | 96.7% | 100.0% | 3,933 | 2,601 | 189 | $0.00169 | $1.69 | 15.9 s | 16.1 s |
| `gpt-6-luna+reasoning_effort=low` | native | 39 | 99.1% | 87.2% | 97.6% | 100.0% | 5,232 | 2,799 | 348 | $0.00192 | $1.92 | 18.8 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 39 | 98.3% | 84.6% | 98.3% | 100.0% | 7,264 | 2,638 | 231 | $0.00205 | $2.05 | 16.5 s | n/a |

### Against the text route

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | native | 1.33x | 1.02x | -2.0 pp | +10.3 pp |
| `gpt-6-luna` | hybrid | 1.85x | 1.17x | -2.3 pp | +10.3 pp |
| `gpt-6-luna+reasoning_effort=low` | native | 1.33x | 1.14x | -0.9 pp | +15.4 pp |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 1.85x | 1.21x | -1.7 pp | +12.8 pp |

## scan=digital

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | text | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,304 | 3,239 | 0 | $0.00195 | $1.95 | 25.4 s | 0.6 s |
| `gpt-6-luna` | native | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 4,488 | 2,854 | 0 | $0.00188 | $1.88 | 21.3 s | n/a |
| `gpt-6-luna` | hybrid | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,553 | 3,144 | 0 | $0.00193 | $1.93 | 22.7 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | text | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,304 | 2,981 | 95 | $0.00182 | $1.82 | 19.8 s | 0.6 s |
| `gpt-6-luna+reasoning_effort=low` | native | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 4,488 | 2,991 | 70 | $0.00194 | $1.94 | 18.8 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,553 | 2,996 | 96 | $0.00185 | $1.85 | 19.8 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | native | 1.36x | 0.96x | +0.0 pp | +0.0 pp |
| `gpt-6-luna` | hybrid | 1.08x | 0.99x | +0.0 pp | +0.0 pp |
| `gpt-6-luna+reasoning_effort=low` | native | 1.36x | 1.07x | +0.0 pp | +0.0 pp |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 1.08x | 1.02x | +0.0 pp | +0.0 pp |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | text | 29 | 100.0% | 65.5% | 93.7% | 100.0% | 4,150 | 2,355 | 0 | $0.00159 | $1.59 | 15.7 s | 21.4 s |
| `gpt-6-luna` | native | 29 | 97.3% | 79.3% | 98.2% | 100.0% | 5,488 | 2,210 | 0 | $0.00165 | $1.65 | 15.6 s | n/a |
| `gpt-6-luna` | hybrid | 29 | 96.9% | 79.3% | 99.7% | 100.0% | 8,543 | 2,251 | 0 | $0.00198 | $1.98 | 15.1 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | text | 29 | 100.0% | 62.1% | 95.1% | 100.0% | 4,150 | 2,469 | 222 | $0.00165 | $1.65 | 14.5 s | 21.4 s |
| `gpt-6-luna+reasoning_effort=low` | native | 29 | 98.9% | 82.8% | 96.6% | 100.0% | 5,488 | 2,733 | 444 | $0.00192 | $1.92 | 18.9 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 29 | 97.7% | 79.3% | 97.5% | 100.0% | 8,543 | 2,515 | 278 | $0.00211 | $2.11 | 16.1 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | native | 1.32x | 1.04x | -2.7 pp | +13.8 pp |
| `gpt-6-luna` | hybrid | 2.06x | 1.24x | -3.1 pp | +13.8 pp |
| `gpt-6-luna+reasoning_effort=low` | native | 1.32x | 1.16x | -1.1 pp | +20.7 pp |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 2.06x | 1.28x | -2.3 pp | +17.2 pp |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | text | 10 | 100.0% | 60.0% | 84.6% | 100.0% | 6,026 | 1,347 | 0 | $0.00128 | $1.28 | 10.2 s | 25.7 s |
| `gpt-6-luna` | native | 10 | 96.7% | 70.0% | 98.4% | 100.0% | 8,669 | 1,531 | 0 | $0.00163 | $1.63 | 12.9 s | n/a |
| `gpt-6-luna` | hybrid | 10 | 95.6% | 70.0% | 99.5% | 100.0% | 12,500 | 1,528 | 0 | $0.00201 | $2.01 | 12.3 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | text | 10 | 100.0% | 50.0% | 86.4% | 100.0% | 6,026 | 1,784 | 270 | $0.00149 | $1.49 | 12.7 s | 25.7 s |
| `gpt-6-luna+reasoning_effort=low` | native | 10 | 98.9% | 70.0% | 92.4% | 100.0% | 8,669 | 2,070 | 542 | $0.00190 | $1.90 | 17.0 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 10 | 96.7% | 70.0% | 95.0% | 100.0% | 12,500 | 1,840 | 246 | $0.00217 | $2.17 | 12.7 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | native | 1.44x | 1.28x | -3.3 pp | +10.0 pp |
| `gpt-6-luna` | hybrid | 2.07x | 1.58x | -4.4 pp | +10.0 pp |
| `gpt-6-luna+reasoning_effort=low` | native | 1.44x | 1.27x | -1.1 pp | +20.0 pp |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 2.07x | 1.45x | -3.3 pp | +20.0 pp |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | text | 29 | 100.0% | 79.3% | 97.6% | 100.0% | 3,211 | 3,007 | 0 | $0.00182 | $1.82 | 19.6 s | 12.8 s |
| `gpt-6-luna` | native | 29 | 98.5% | 89.7% | 98.8% | 100.0% | 4,047 | 2,666 | 0 | $0.00174 | $1.74 | 20.4 s | n/a |
| `gpt-6-luna` | hybrid | 29 | 98.5% | 89.7% | 99.9% | 100.0% | 5,458 | 2,808 | 0 | $0.00195 | $1.95 | 19.8 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | text | 29 | 100.0% | 79.3% | 98.6% | 100.0% | 3,211 | 2,882 | 162 | $0.00176 | $1.76 | 17.9 s | 12.8 s |
| `gpt-6-luna+reasoning_effort=low` | native | 29 | 99.2% | 93.1% | 98.6% | 100.0% | 4,047 | 3,050 | 281 | $0.00193 | $1.93 | 20.0 s | n/a |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 29 | 98.9% | 89.7% | 98.9% | 100.0% | 5,458 | 2,914 | 226 | $0.00200 | $2.00 | 17.7 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | native | 1.26x | 0.95x | -1.5 pp | +10.3 pp |
| `gpt-6-luna` | hybrid | 1.70x | 1.07x | -1.5 pp | +10.3 pp |
| `gpt-6-luna+reasoning_effort=low` | native | 1.26x | 1.10x | -0.8 pp | +13.8 pp |
| `gpt-6-luna+reasoning_effort=low` | hybrid | 1.70x | 1.14x | -1.1 pp | +10.3 pp |
