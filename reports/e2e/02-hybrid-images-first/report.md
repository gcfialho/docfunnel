# End-to-end evaluation: hybrid route, 29 invoices with scanned pages

- Dataset: `data/synthetic/e2e`: 29 invoices, 146 pages
- Models: `gemini:gemini-3.5-flash-lite`, `anthropic:claude-haiku-5-5`, `gemini:gemini-3.1-flash-lite`; routes: hybrid
- Spend: gemini $0.44 of $0.80, anthropic $0.10 of $0.80; skipped calls (budget reached or provider stopped): 0
- Package `0.1.0`, prompt `v2`, created 2026-11-17T20:18:01+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | hybrid | 29 | 93.5% | 75.9% | 92.3% | 100.0% | 5,130 | 3,070 | 0 | $0.00921 | $9.21 | 7.1 s | n/a |
| `claude-haiku-5-5` | hybrid | 29 | 100.0% | 79.3% | 89.9% | 100.0% | 11,448 | 4,910 | n/a | $0.00360 | $3.60 | 14.6 s | n/a |
| `gemini-3.1-flash-lite` | hybrid | 29 | 98.9% | 55.2% | 87.0% | 100.0% | 5,130 | 3,072 | 0 | $0.00589 | $5.89 | 6.7 s | n/a |

### Against the text route

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | hybrid | 29 | 93.5% | 75.9% | 92.3% | 100.0% | 5,130 | 3,070 | 0 | $0.00921 | $9.21 | 7.1 s | n/a |
| `claude-haiku-5-5` | hybrid | 29 | 100.0% | 79.3% | 89.9% | 100.0% | 11,448 | 4,910 | n/a | $0.00360 | $3.60 | 14.6 s | n/a |
| `gemini-3.1-flash-lite` | hybrid | 29 | 98.9% | 55.2% | 87.0% | 100.0% | 5,130 | 3,072 | 0 | $0.00589 | $5.89 | 6.7 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | hybrid | 10 | 81.1% | 60.0% | 84.8% | 100.0% | 7,708 | 1,923 | 0 | $0.00712 | $7.12 | 6.1 s | n/a |
| `claude-haiku-5-5` | hybrid | 10 | 100.0% | 80.0% | 88.7% | 100.0% | 16,784 | 3,665 | n/a | $0.00351 | $3.51 | 13.4 s | n/a |
| `gemini-3.1-flash-lite` | hybrid | 10 | 97.8% | 50.0% | 81.5% | 100.0% | 7,708 | 2,246 | 0 | $0.00530 | $5.30 | 6.4 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | hybrid | 19 | 100.0% | 84.2% | 94.4% | 100.0% | 3,773 | 3,673 | 0 | $0.01032 | $10.32 | 7.6 s | n/a |
| `claude-haiku-5-5` | hybrid | 19 | 100.0% | 78.9% | 90.2% | 100.0% | 8,640 | 5,565 | n/a | $0.00365 | $3.65 | 15.7 s | n/a |
| `gemini-3.1-flash-lite` | hybrid | 19 | 99.4% | 57.9% | 88.5% | 100.0% | 3,773 | 3,507 | 0 | $0.00620 | $6.20 | 7.7 s | n/a |

| Model | Route | Input tokens (route / text) | Cost (route / text) | Field accuracy (route - text) | Exact match (route - text) |
| --- | --- | ---: | ---: | ---: | ---: |
