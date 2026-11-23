# End-to-end evaluation: 4 small models, 39 invoices (29 small, 10 large)

- Dataset: `data/synthetic/e2e`: 39 invoices, 174 pages
- Models: `gemini:gemini-3.5-flash-lite`, `gemini:gemini-3.8-flash`, `anthropic:claude-haiku-5-5`, `gemini:gemini-3.1-flash-lite`; routes: docfunnel, native
- Spend: gemini $2.67 of $3.80, anthropic $0.29 of $3.80; skipped calls (budget reached): 0
- Package `0.1.0`, prompt `v2`, created 2026-11-17T20:04:07+00:00

**docfunnel**: the parse stage reads the PDF on the CPU and the model gets text. **native**: the PDF goes to the model as a file. Same prompt, schema, repair turn and scoring. Cost per 1k docs is the measured cost per document times 1,000. LLM p50 is the model's wall-clock time; the parse CPU time is reported apart, per document, summed over its pages.

## All documents

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | docfunnel | 39 | 99.4% | 69.2% | 97.3% | 100.0% | 4,223 | 4,477 | $0.01246 | $12.46 | 7.3 s | 19.7 s |
| `gemini-3.5-flash-lite` | native | 39 | 99.7% | 97.4% | 100.0% | 100.0% | 3,176 | 4,363 | $0.01186 | $11.86 | 8.5 s | n/a |
| `gemini-3.8-flash` | docfunnel | 39 | 99.4% | 64.1% | 95.7% | 100.0% | 4,223 | 3,208 | $0.01520 | $15.20 | 17.1 s | 19.7 s |
| `gemini-3.8-flash` | native | 39 | 100.0% | 97.4% | 100.0% | 100.0% | 3,176 | 3,204 | $0.01440 | $14.40 | 19.8 s | n/a |
| `claude-haiku-5-5` | docfunnel | 39 | 98.0% | 69.2% | 92.7% | 100.0% | 6,541 | 5,121 | $0.00321 | $3.21 | 16.0 s | 19.7 s |
| `claude-haiku-5-5` | native | 39 | 100.0% | 82.1% | 86.5% | 100.0% | 12,121 | 6,156 | $0.00429 | $4.29 | 17.6 s | n/a |
| `gemini-3.1-flash-lite` | docfunnel | 39 | 99.1% | 87.2% | 99.1% | 100.0% | 4,223 | 4,223 | $0.00739 | $7.39 | 8.0 s | 19.7 s |
| `gemini-3.1-flash-lite` | native | 39 | 99.7% | 84.6% | 98.4% | 100.0% | 3,176 | 4,203 | $0.00710 | $7.10 | 9.3 s | n/a |

### Native against docfunnel

| Model | Input tokens (native / docfunnel) | Cost (native / docfunnel) | Field accuracy (docfunnel - native) | Exact match (docfunnel - native) |
| --- | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | 0.75x | 0.95x | -0.3 pp | -28.2 pp |
| `gemini-3.8-flash` | 0.75x | 0.95x | -0.6 pp | -33.3 pp |
| `claude-haiku-5-5` | 1.85x | 1.33x | -2.0 pp | -12.8 pp |
| `gemini-3.1-flash-lite` | 0.75x | 0.96x | -0.6 pp | +2.6 pp |

## scan=digital

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | docfunnel | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,664 | 5,451 | $0.01473 | $14.73 | 10.8 s | 0.8 s |
| `gemini-3.5-flash-lite` | native | 10 | 98.9% | 90.0% | 100.0% | 100.0% | 2,297 | 5,541 | $0.01454 | $14.54 | 11.5 s | n/a |
| `gemini-3.8-flash` | docfunnel | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,664 | 3,845 | $0.01717 | $17.17 | 21.4 s | 0.8 s |
| `gemini-3.8-flash` | native | 10 | 100.0% | 90.0% | 99.9% | 100.0% | 2,297 | 3,845 | $0.01614 | $16.14 | 24.1 s | n/a |
| `claude-haiku-5-5` | docfunnel | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 5,355 | 6,112 | $0.00359 | $3.59 | 18.4 s | 0.8 s |
| `claude-haiku-5-5` | native | 10 | 100.0% | 70.0% | 74.0% | 100.0% | 9,698 | 7,604 | $0.00477 | $4.77 | 25.3 s | n/a |
| `gemini-3.1-flash-lite` | docfunnel | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 3,664 | 4,914 | $0.00829 | $8.29 | 9.7 s | 0.8 s |
| `gemini-3.1-flash-lite` | native | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 2,297 | 5,000 | $0.00807 | $8.07 | 10.5 s | n/a |

| Model | Input tokens (native / docfunnel) | Cost (native / docfunnel) | Field accuracy (docfunnel - native) | Exact match (docfunnel - native) |
| --- | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | 0.63x | 0.99x | +1.1 pp | +10.0 pp |
| `gemini-3.8-flash` | 0.63x | 0.94x | +0.0 pp | +10.0 pp |
| `claude-haiku-5-5` | 1.81x | 1.33x | +0.0 pp | +30.0 pp |
| `gemini-3.1-flash-lite` | 0.63x | 0.97x | +0.0 pp | +0.0 pp |

## scan=has_scanned_pages

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | docfunnel | 29 | 99.2% | 58.6% | 96.1% | 100.0% | 4,415 | 4,142 | $0.01168 | $11.68 | 7.0 s | 26.2 s |
| `gemini-3.5-flash-lite` | native | 29 | 100.0% | 100.0% | 100.0% | 100.0% | 3,480 | 3,956 | $0.01093 | $10.93 | 7.7 s | n/a |
| `gemini-3.8-flash` | docfunnel | 29 | 99.2% | 51.7% | 93.8% | 100.0% | 4,415 | 2,989 | $0.01452 | $14.52 | 16.9 s | 26.2 s |
| `gemini-3.8-flash` | native | 29 | 100.0% | 100.0% | 100.0% | 100.0% | 3,480 | 2,983 | $0.01380 | $13.80 | 19.7 s | n/a |
| `claude-haiku-5-5` | docfunnel | 29 | 97.3% | 58.6% | 89.1% | 100.0% | 6,949 | 4,779 | $0.00308 | $3.08 | 15.7 s | 26.2 s |
| `claude-haiku-5-5` | native | 29 | 100.0% | 86.2% | 92.4% | 100.0% | 12,956 | 5,657 | $0.00412 | $4.12 | 16.9 s | n/a |
| `gemini-3.1-flash-lite` | docfunnel | 29 | 98.9% | 82.8% | 98.7% | 100.0% | 4,415 | 3,985 | $0.00708 | $7.08 | 7.7 s | 26.2 s |
| `gemini-3.1-flash-lite` | native | 29 | 99.6% | 79.3% | 97.7% | 100.0% | 3,480 | 3,928 | $0.00676 | $6.76 | 8.9 s | n/a |

| Model | Input tokens (native / docfunnel) | Cost (native / docfunnel) | Field accuracy (docfunnel - native) | Exact match (docfunnel - native) |
| --- | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | 0.79x | 0.94x | -0.8 pp | -41.4 pp |
| `gemini-3.8-flash` | 0.79x | 0.95x | -0.8 pp | -48.3 pp |
| `claude-haiku-5-5` | 1.86x | 1.34x | -2.7 pp | -27.6 pp |
| `gemini-3.1-flash-lite` | 0.79x | 0.95x | -0.8 pp | +3.4 pp |

## size=large

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | docfunnel | 10 | 98.9% | 40.0% | 91.5% | 100.0% | 6,210 | 2,656 | $0.00850 | $8.50 | 5.4 s | 32.9 s |
| `gemini-3.5-flash-lite` | native | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 5,851 | 2,330 | $0.00758 | $7.58 | 6.6 s | n/a |
| `gemini-3.8-flash` | docfunnel | 10 | 98.9% | 50.0% | 87.3% | 100.0% | 6,210 | 2,051 | $0.01235 | $12.35 | 14.3 s | 32.9 s |
| `gemini-3.8-flash` | native | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 5,851 | 2,054 | $0.01209 | $12.09 | 18.5 s | n/a |
| `claude-haiku-5-5` | docfunnel | 10 | 96.7% | 50.0% | 81.6% | 100.0% | 10,284 | 3,470 | $0.00276 | $2.76 | 11.0 s | 32.9 s |
| `claude-haiku-5-5` | native | 10 | 100.0% | 80.0% | 95.3% | 100.0% | 22,656 | 4,480 | $0.00451 | $4.51 | 16.3 s | n/a |
| `gemini-3.1-flash-lite` | docfunnel | 10 | 97.8% | 70.0% | 95.3% | 100.0% | 6,210 | 3,019 | $0.00608 | $6.08 | 7.3 s | 32.9 s |
| `gemini-3.1-flash-lite` | native | 10 | 98.9% | 90.0% | 100.0% | 100.0% | 5,851 | 3,158 | $0.00620 | $6.20 | 8.6 s | n/a |

| Model | Input tokens (native / docfunnel) | Cost (native / docfunnel) | Field accuracy (docfunnel - native) | Exact match (docfunnel - native) |
| --- | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | 0.94x | 0.89x | -1.1 pp | -60.0 pp |
| `gemini-3.8-flash` | 0.94x | 0.98x | -1.1 pp | -50.0 pp |
| `claude-haiku-5-5` | 2.20x | 1.63x | -3.3 pp | -30.0 pp |
| `gemini-3.1-flash-lite` | 0.94x | 1.02x | -1.1 pp | -20.0 pp |

## size=small

| Model | Route | Docs | Field accuracy | Exact match | Line items F1 | Schema valid | Input tok/doc | Output tok/doc | Cost/doc | Cost per 1k docs | LLM p50 | Parse CPU/doc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | docfunnel | 29 | 99.6% | 79.3% | 98.4% | 100.0% | 3,538 | 5,105 | $0.01382 | $13.82 | 8.9 s | 15.1 s |
| `gemini-3.5-flash-lite` | native | 29 | 99.6% | 96.6% | 100.0% | 100.0% | 2,254 | 5,063 | $0.01333 | $13.33 | 10.5 s | n/a |
| `gemini-3.8-flash` | docfunnel | 29 | 99.6% | 69.0% | 97.3% | 100.0% | 3,538 | 3,607 | $0.01618 | $16.18 | 19.7 s | 15.1 s |
| `gemini-3.8-flash` | native | 29 | 100.0% | 96.6% | 100.0% | 100.0% | 2,254 | 3,600 | $0.01519 | $15.19 | 21.1 s | n/a |
| `claude-haiku-5-5` | docfunnel | 29 | 98.5% | 75.9% | 94.6% | 100.0% | 5,250 | 5,690 | $0.00337 | $3.37 | 17.6 s | 15.1 s |
| `claude-haiku-5-5` | native | 29 | 100.0% | 82.8% | 84.8% | 100.0% | 8,488 | 6,734 | $0.00422 | $4.22 | 18.7 s | n/a |
| `gemini-3.1-flash-lite` | docfunnel | 29 | 99.6% | 93.1% | 99.8% | 100.0% | 3,538 | 4,639 | $0.00784 | $7.84 | 8.7 s | 15.1 s |
| `gemini-3.1-flash-lite` | native | 29 | 100.0% | 82.8% | 98.1% | 100.0% | 2,254 | 4,564 | $0.00741 | $7.41 | 10.1 s | n/a |

| Model | Input tokens (native / docfunnel) | Cost (native / docfunnel) | Field accuracy (docfunnel - native) | Exact match (docfunnel - native) |
| --- | ---: | ---: | ---: | ---: |
| `gemini-3.5-flash-lite` | 0.64x | 0.96x | +0.0 pp | -17.2 pp |
| `gemini-3.8-flash` | 0.64x | 0.94x | -0.4 pp | -27.6 pp |
| `claude-haiku-5-5` | 1.62x | 1.25x | -1.5 pp | -6.9 pp |
| `gemini-3.1-flash-lite` | 0.64x | 0.94x | -0.4 pp | +10.3 pp |
