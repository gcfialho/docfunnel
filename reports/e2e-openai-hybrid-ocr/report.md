# End-to-end evaluation: GPT-6 Luna, hybrid with OCR text, all 39 invoices

- Dataset: `data/synthetic/e2e`: 39 invoices, 174 pages
- Models: `openai:gpt-6-luna`; routes: docfunnel, hybrid, hybrid-ocr
- Spend: openai $0.18 of $0.50; skipped calls (budget reached or provider stopped): 0
- Package `0.1.0`, prompt `v2`, created 2026-11-17T22:30:10+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | docfunnel | 39 | 100.0% | 71.8% | 91.0% | 100.0% | 3,933 | 2,149 | 0 | $0.00147 | $1.47 | 15.0 s | 40.7 s |
| `gpt-6-luna` | hybrid | 39 | 97.7% | 79.5% | 94.6% | 100.0% | 7,264 | 2,249 | 0 | $0.00185 | $1.85 | 16.1 s | n/a |
| `gpt-6-luna` | hybrid-ocr | 39 | 100.0% | 100.0% | 100.0% | 100.0% | 8,349 | 2,634 | 0 | $0.00215 | $2.15 | 18.5 s | n/a |

### Against the docfunnel route

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid | 1.85x | 1.26x | -2.3 pp | +7.7 pp |
| `gpt-6-luna` | hybrid-ocr | 2.12x | 1.47x | +0.0 pp | +28.2 pp |

## scan=digital

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | docfunnel | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,304 | 3,013 | 0 | $0.00184 | $1.84 | 22.2 s | 6.5 s |
| `gpt-6-luna` | hybrid | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,553 | 2,999 | 0 | $0.00185 | $1.85 | 22.2 s | n/a |
| `gpt-6-luna` | hybrid-ocr | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,563 | 3,013 | 0 | $0.00186 | $1.86 | 22.2 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid | 1.08x | 1.01x | +0.0 pp | +0.0 pp |
| `gpt-6-luna` | hybrid-ocr | 1.08x | 1.01x | +0.0 pp | +0.0 pp |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | docfunnel | 29 | 100.0% | 62.1% | 86.4% | 100.0% | 4,150 | 1,851 | 0 | $0.00134 | $1.34 | 14.7 s | 52.5 s |
| `gpt-6-luna` | hybrid | 29 | 96.9% | 72.4% | 92.0% | 100.0% | 8,543 | 1,991 | 0 | $0.00185 | $1.85 | 15.6 s | n/a |
| `gpt-6-luna` | hybrid-ocr | 29 | 100.0% | 100.0% | 100.0% | 100.0% | 9,999 | 2,504 | 0 | $0.00225 | $2.25 | 17.1 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid | 2.06x | 1.38x | -3.1 pp | +10.3 pp |
| `gpt-6-luna` | hybrid-ocr | 2.41x | 1.68x | +0.0 pp | +37.9 pp |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | docfunnel | 10 | 100.0% | 70.0% | 92.0% | 100.0% | 6,026 | 1,406 | 0 | $0.00131 | $1.31 | 12.8 s | 32.8 s |
| `gpt-6-luna` | hybrid | 10 | 96.7% | 80.0% | 96.4% | 100.0% | 12,500 | 1,539 | 0 | $0.00202 | $2.02 | 12.2 s | n/a |
| `gpt-6-luna` | hybrid-ocr | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 14,296 | 1,610 | 0 | $0.00223 | $2.23 | 14.0 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid | 2.07x | 1.55x | -3.3 pp | +10.0 pp |
| `gpt-6-luna` | hybrid-ocr | 2.37x | 1.71x | +0.0 pp | +30.0 pp |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | docfunnel | 29 | 100.0% | 72.4% | 90.8% | 100.0% | 3,211 | 2,406 | 0 | $0.00152 | $1.52 | 16.0 s | 43.5 s |
| `gpt-6-luna` | hybrid | 29 | 98.1% | 79.3% | 94.3% | 100.0% | 5,458 | 2,494 | 0 | $0.00179 | $1.79 | 19.3 s | n/a |
| `gpt-6-luna` | hybrid-ocr | 29 | 100.0% | 100.0% | 100.0% | 100.0% | 6,298 | 2,987 | 0 | $0.00212 | $2.12 | 21.4 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid | 1.70x | 1.18x | -1.9 pp | +6.9 pp |
| `gpt-6-luna` | hybrid-ocr | 1.96x | 1.39x | +0.0 pp | +27.6 pp |
