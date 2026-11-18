# Developer shortcuts. Every target is a thin wrapper over `uv run`, so CI and local
# runs execute the same commands. `make help` lists them.

.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test cov check \
        pdfs eval eval-parse gate gate-parse baselines e2e-summary serve docker clean

UV ?= uv

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- setup & quality -------------------------------------------------------------

install: ## Install every extra and the dev tools (needs uv)
	$(UV) sync --all-extras

lint: ## Ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Apply ruff fixes and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck: ## mypy --strict over src/ and tests/
	$(UV) run mypy

test: ## Run the test suite (offline, no API keys)
	$(UV) run pytest

cov: ## Tests with line coverage
	$(UV) run pytest --cov=docfunnel --cov-report=term-missing

check: lint typecheck test ## Everything the CI lint-and-test job runs

# ---- evaluations ------------------------------------------------------------------

pdfs: ## Generate the synthetic PDF set (data/synthetic/pdf)
	$(UV) run docfunnel generate-pdfs

eval: ## LLM-step eval with the fake provider -> reports/latest
	$(UV) run docfunnel eval --provider fake --model fake-mini --fallback fake:fake-pro

gate: eval ## LLM-step eval, then compare against the committed baseline
	$(UV) run docfunnel compare reports/baseline/fake-mini+fallback/report.json reports/latest/report.json

eval-parse: pdfs ## Parse-stage eval with RapidOCR -> reports/parse-latest
	$(UV) run docfunnel eval-parse --ocr-engine rapidocr

gate-parse: eval-parse ## Parse-stage eval, then compare against the committed baseline
	$(UV) run docfunnel compare-parse reports/baseline/parse/report.json reports/parse-latest/report.json

baselines: ## Rewrite the committed LLM-step baselines (parse baseline: see CONTRIBUTING.md)
	DOCFUNNEL_FALLBACK= $(UV) run docfunnel eval --provider fake --model fake-mini \
		--out reports/baseline/fake-mini --run-name "fake-mini (no fallback)"
	$(UV) run docfunnel eval --provider fake --model fake-mini --fallback fake:fake-pro \
		--out reports/baseline/fake-mini+fallback --run-name "fake-mini + fake-pro fallback"

e2e-summary: ## Regenerate reports/e2e/README.md and the accuracy-vs-cost chart
	$(UV) run docfunnel e2e-summary reports/e2e

# ---- run --------------------------------------------------------------------------

serve: ## FastAPI on http://127.0.0.1:8000 (docs at /docs)
	$(UV) run docfunnel serve

docker: ## Build the image and run the same smoke tests as CI
	docker build -t docfunnel .
	docker run --rm docfunnel docfunnel extract examples/receipt_us.txt --no-include-calls
	docker run --rm docfunnel docfunnel parse examples/invoice_multipage.pdf

clean: ## Remove caches and local reports (keeps reports/baseline)
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov coverage.xml dist build
	find reports -mindepth 1 -maxdepth 1 ! -name baseline -exec rm -rf {} +
	find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +
