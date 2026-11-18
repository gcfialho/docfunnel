# End-to-end evaluation: Gemma 4 12B on Ollama (local), 12-invoice sample

- Dataset: `data/synthetic/e2e`: 12 invoices, 54 pages
- Models: `ollama:gemma4:12b-mlx`; routes: docfunnel, hybrid, hybrid-ocr
- Spend: ollama $0.00 of $4.00; skipped calls (budget reached or provider stopped): 0
- Package `0.1.0`, prompt `v2`, created 2026-11-18T00:32:18+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | docfunnel | 12 | 99.1% | 58.3% | 92.6% | 100.0% | 4,410 | 4,368 | n/a | $0.00000 | $0.00 | 415.0 s | 94.2 s |
| `gemma4:12b-mlx` | hybrid | 12 | 86.1% | 33.3% | 90.9% | 100.0% | 4,840 | 3,725 | n/a | $0.00000 | $0.00 | 311.5 s | n/a |
| `gemma4:12b-mlx` | hybrid-ocr | 12 | 99.1% | 66.7% | 96.2% | 100.0% | 6,289 | 4,395 | n/a | $0.00000 | $0.00 | 390.2 s | n/a |

### Against the docfunnel route

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | hybrid | 1.10x | n/a | -13.0 pp | -25.0 pp |
| `gemma4:12b-mlx` | hybrid-ocr | 1.43x | n/a | +0.0 pp | +8.3 pp |

## scan=digital

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | docfunnel | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 5,434 | 7,406 | n/a | $0.00000 | $0.00 | 1052.1 s | 0.8 s |
| `gemma4:12b-mlx` | hybrid | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 5,434 | 7,406 | n/a | $0.00000 | $0.00 | 1052.1 s | n/a |
| `gemma4:12b-mlx` | hybrid-ocr | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 5,434 | 7,406 | n/a | $0.00000 | $0.00 | 1052.1 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | hybrid | 1.00x | n/a | +0.0 pp | +0.0 pp |
| `gemma4:12b-mlx` | hybrid-ocr | 1.00x | n/a | +0.0 pp | +0.0 pp |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | docfunnel | 10 | 98.9% | 50.0% | 89.4% | 100.0% | 4,206 | 3,760 | n/a | $0.00000 | $0.00 | 313.7 s | 112.9 s |
| `gemma4:12b-mlx` | hybrid | 10 | 83.3% | 20.0% | 86.4% | 100.0% | 4,721 | 2,989 | n/a | $0.00000 | $0.00 | 284.4 s | n/a |
| `gemma4:12b-mlx` | hybrid-ocr | 10 | 98.9% | 60.0% | 94.5% | 100.0% | 6,460 | 3,793 | n/a | $0.00000 | $0.00 | 346.5 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | hybrid | 1.12x | n/a | -15.6 pp | -30.0 pp |
| `gemma4:12b-mlx` | hybrid-ocr | 1.54x | n/a | +0.0 pp | +10.0 pp |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | docfunnel | 3 | 96.3% | 33.3% | 83.4% | 100.0% | 6,461 | 2,645 | n/a | $0.00000 | $0.00 | 302.6 s | 76.8 s |
| `gemma4:12b-mlx` | hybrid | 3 | 63.0% | 0.0% | 64.1% | 100.0% | 8,017 | 1,428 | n/a | $0.00000 | $0.00 | 141.7 s | n/a |
| `gemma4:12b-mlx` | hybrid-ocr | 3 | 100.0% | 66.7% | 85.1% | 100.0% | 9,834 | 2,310 | n/a | $0.00000 | $0.00 | 378.2 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | hybrid | 1.24x | n/a | -33.3 pp | -33.3 pp |
| `gemma4:12b-mlx` | hybrid-ocr | 1.52x | n/a | +3.7 pp | +33.3 pp |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | of which thinking | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | docfunnel | 9 | 100.0% | 66.7% | 94.5% | 100.0% | 3,727 | 4,942 | n/a | $0.00000 | $0.00 | 641.6 s | 100.0 s |
| `gemma4:12b-mlx` | hybrid | 9 | 93.8% | 44.4% | 95.2% | 100.0% | 3,781 | 4,490 | n/a | $0.00000 | $0.00 | 454.5 s | n/a |
| `gemma4:12b-mlx` | hybrid-ocr | 9 | 98.8% | 66.7% | 98.3% | 100.0% | 5,107 | 5,091 | n/a | $0.00000 | $0.00 | 604.5 s | n/a |

| Model | Route | Input tokens (route / docfunnel) | Cost (route / docfunnel) | Field accuracy (route - docfunnel) | Exact match (route - docfunnel) |
| --- | --- | ---: | ---: | ---: | ---: |
| `gemma4:12b-mlx` | hybrid | 1.01x | n/a | -6.2 pp | -22.2 pp |
| `gemma4:12b-mlx` | hybrid-ocr | 1.37x | n/a | -1.2 pp | +0.0 pp |
