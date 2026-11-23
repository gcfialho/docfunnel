# End-to-end evaluation: hybrid route with compact line items, 39 invoices (Haiku only: the Gemini key ran out of prepaid credit)

- Dataset: `data/synthetic/e2e`: 39 invoices, 174 pages
- Models: `anthropic:claude-haiku-5-5`; routes: hybrid
- Spend: anthropic $0.14 of $0.45; skipped calls (budget reached or provider stopped): 0
- **gemini stopped**: repeated calls failed without using a token: 402 RESOURCE_EXHAUSTED: prepayment credits are depleted
- Package `0.1.0`, prompt `v2-compact`, created 2026-11-17T20:31:17+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5` | hybrid | 39 | 99.7% | 89.7% | 98.1% | 100.0% | 9,923 | 5,274 | n/a | $0.00363 | $3.63 | 14.7 s | n/a |

### Against the docfunnel route

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## scan=digital

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5` | hybrid | 10 | 98.9% | 90.0% | 100.0% | 100.0% | 5,611 | 5,960 | n/a | $0.00354 | $3.54 | 19.9 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5` | hybrid | 29 | 100.0% | 89.7% | 97.2% | 100.0% | 11,410 | 5,037 | n/a | $0.00366 | $3.66 | 14.4 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5` | hybrid | 10 | 100.0% | 90.0% | 95.9% | 100.0% | 16,737 | 3,876 | n/a | $0.00361 | $3.61 | 13.6 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-haiku-5-5` | hybrid | 29 | 99.6% | 89.7% | 98.5% | 100.0% | 7,574 | 5,756 | n/a | $0.00364 | $3.64 | 17.5 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
