# End-to-end evaluation: Sonnet 5.5 and Haiku 5.5 at effort medium, 12-invoice sample

- Dataset: `data/synthetic/e2e`: 12 invoices, 54 pages
- Models: `anthropic:claude-haiku-5-5+effort=medium`, `anthropic:claude-sonnet-5-5`; routes: native, hybrid
- Spend: anthropic $1.37 of $2.40; skipped calls (budget reached or provider stopped): 0
- Package `0.1.0`, prompt `v2`, created 2026-11-17T20:39:36+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5+effort=medium` | native | 12 | 100.0% | 91.7% | 92.6% | 100.0% | 12,302 | 6,505 | n/a | $0.00448 | $4.48 | 17.3 s | n/a |
| `claude-haiku-5-5+effort=medium` | hybrid | 12 | 100.0% | 100.0% | 100.0% | 100.0% | 9,908 | 6,807 | n/a | $0.00439 | $4.39 | 17.7 s | n/a |
| `claude-sonnet-5-5` | native | 12 | 100.0% | 75.0% | 78.9% | 100.0% | 12,302 | 2,907 | n/a | $0.05367 | $53.67 | 12.8 s | n/a |
| `claude-sonnet-5-5` | hybrid | 12 | 100.0% | 75.0% | 85.1% | 100.0% | 9,908 | 3,182 | n/a | $0.05163 | $51.63 | 14.0 s | n/a |

### Against the text route

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |

## scan=digital

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5+effort=medium` | native | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 13,081 | 13,218 | n/a | $0.00792 | $7.92 | 40.2 s | n/a |
| `claude-haiku-5-5+effort=medium` | hybrid | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 6,873 | 11,205 | n/a | $0.00629 | $6.29 | 32.2 s | n/a |
| `claude-sonnet-5-5` | native | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 13,081 | 8,042 | n/a | $0.10659 | $106.59 | 38.4 s | n/a |
| `claude-sonnet-5-5` | hybrid | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 6,873 | 7,584 | n/a | $0.08959 | $89.59 | 34.6 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5+effort=medium` | native | 10 | 100.0% | 90.0% | 89.1% | 100.0% | 12,147 | 5,163 | n/a | $0.00380 | $3.80 | 16.1 s | n/a |
| `claude-haiku-5-5+effort=medium` | hybrid | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 10,515 | 5,928 | n/a | $0.00402 | $4.02 | 15.6 s | n/a |
| `claude-sonnet-5-5` | native | 10 | 100.0% | 70.0% | 66.7% | 100.0% | 12,147 | 1,880 | n/a | $0.04309 | $43.09 | 11.2 s | n/a |
| `claude-sonnet-5-5` | hybrid | 10 | 100.0% | 70.0% | 77.1% | 100.0% | 10,515 | 2,301 | n/a | $0.04404 | $44.04 | 12.0 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5+effort=medium` | native | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 23,631 | 5,471 | n/a | $0.00510 | $5.10 | 18.2 s | n/a |
| `claude-haiku-5-5+effort=medium` | hybrid | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 16,901 | 5,452 | n/a | $0.00442 | $4.42 | 19.6 s | n/a |
| `claude-sonnet-5-5` | native | 3 | 100.0% | 66.7% | 73.9% | 100.0% | 23,631 | 2,156 | n/a | $0.06883 | $68.83 | 11.9 s | n/a |
| `claude-sonnet-5-5` | hybrid | 3 | 100.0% | 33.3% | 46.8% | 100.0% | 16,901 | 1,005 | n/a | $0.04385 | $43.85 | 2.6 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5+effort=medium` | native | 9 | 100.0% | 88.9% | 90.9% | 100.0% | 8,526 | 6,850 | n/a | $0.00428 | $4.28 | 15.9 s | n/a |
| `claude-haiku-5-5+effort=medium` | hybrid | 9 | 100.0% | 100.0% | 100.0% | 100.0% | 7,577 | 7,259 | n/a | $0.00439 | $4.39 | 15.9 s | n/a |
| `claude-sonnet-5-5` | native | 9 | 100.0% | 77.8% | 79.9% | 100.0% | 8,526 | 3,157 | n/a | $0.04862 | $48.62 | 13.8 s | n/a |
| `claude-sonnet-5-5` | hybrid | 9 | 100.0% | 88.9% | 90.8% | 100.0% | 7,577 | 3,907 | n/a | $0.05423 | $54.23 | 14.3 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |
