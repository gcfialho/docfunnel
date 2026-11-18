# End-to-end evaluation: hybrid-ocr repeat: GPT-6 Luna, 29 invoices with scans (Anthropic rows removed: its key returned 401)

- Dataset: `data/synthetic/e2e`: 29 invoices, 146 pages
- Models: `openai:gpt-6-luna`; routes: hybrid-ocr
- Spend: openai $0.06 of $0.60; skipped calls (budget reached or provider stopped): 0
- Package `0.1.0`, prompt `v2`, created 2026-11-17T22:36:53+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid-ocr | 29 | 100.0% | 96.6% | 97.2% | 100.0% | 9,999 | 2,203 | 0 | $0.00210 | $2.10 | 15.0 s | n/a |

### Against the docfunnel route

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid-ocr | 29 | 100.0% | 96.6% | 97.2% | 100.0% | 9,999 | 2,203 | 0 | $0.00210 | $2.10 | 15.0 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid-ocr | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 14,296 | 1,544 | 0 | $0.00220 | $2.20 | 12.4 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-luna` | hybrid-ocr | 19 | 100.0% | 94.7% | 96.3% | 100.0% | 7,738 | 2,550 | 0 | $0.00205 | $2.05 | 15.7 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
