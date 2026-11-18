# End-to-end evaluation: hybrid route (images in place), 29 invoices with scanned pages

- Dataset: `data/synthetic/e2e`: 29 invoices, 146 pages
- Models: `gemini:gemini-3.5-flash-lite`, `anthropic:claude-haiku-5-5`, `gemini:gemini-3.1-flash-lite`; routes: hybrid
- Spend: gemini $0.53 of $0.70, anthropic $0.10 of $0.70; skipped calls (budget reached): 0
- Package `0.1.0`, prompt `v2`, created 2026-11-17T20:25:52+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | hybrid | 29 | 99.6% | 93.1% | 100.0% | 100.0% | 5,112 | 3,960 | 0 | $0.01143 | $11.43 | 8.6 s | n/a |
| `claude-haiku-5-5` | hybrid | 29 | 100.0% | 75.9% | 91.6% | 100.0% | 11,425 | 4,908 | n/a | $0.00360 | $3.60 | 14.0 s | n/a |
| `gemini-3.1-flash-lite` | hybrid | 29 | 100.0% | 96.6% | 100.0% | 100.0% | 5,112 | 3,809 | 0 | $0.00699 | $6.99 | 8.3 s | n/a |

### Against the docfunnel route

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | hybrid | 29 | 99.6% | 93.1% | 100.0% | 100.0% | 5,112 | 3,960 | 0 | $0.01143 | $11.43 | 8.6 s | n/a |
| `claude-haiku-5-5` | hybrid | 29 | 100.0% | 75.9% | 91.6% | 100.0% | 11,425 | 4,908 | n/a | $0.00360 | $3.60 | 14.0 s | n/a |
| `gemini-3.1-flash-lite` | hybrid | 29 | 100.0% | 96.6% | 100.0% | 100.0% | 5,112 | 3,809 | 0 | $0.00699 | $6.99 | 8.3 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | hybrid | 10 | 98.9% | 90.0% | 100.0% | 100.0% | 7,682 | 2,554 | 0 | $0.00869 | $8.69 | 6.6 s | n/a |
| `claude-haiku-5-5` | hybrid | 10 | 100.0% | 60.0% | 86.1% | 100.0% | 16,752 | 3,274 | n/a | $0.00331 | $3.31 | 10.8 s | n/a |
| `gemini-3.1-flash-lite` | hybrid | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 7,682 | 3,098 | 0 | $0.00657 | $6.57 | 8.3 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | hybrid | 19 | 100.0% | 94.7% | 99.9% | 100.0% | 3,759 | 4,700 | 0 | $0.01288 | $12.88 | 8.9 s | n/a |
| `claude-haiku-5-5` | hybrid | 19 | 100.0% | 84.2% | 93.1% | 100.0% | 8,622 | 5,767 | n/a | $0.00375 | $3.75 | 14.9 s | n/a |
| `gemini-3.1-flash-lite` | hybrid | 19 | 100.0% | 94.7% | 100.0% | 100.0% | 3,759 | 4,184 | 0 | $0.00722 | $7.22 | 8.3 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
