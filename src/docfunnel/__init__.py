"""docfunnel: a CPU-first document pipeline with stage-level evals.

* :mod:`docfunnel.parse`: PDFs and scans to pages and blocks, OCR only where needed.
* :mod:`docfunnel.extract`: schema-validated LLM extraction with repair, fallback and
  review routing.
* :mod:`docfunnel.providers`: OpenAI, Anthropic, Gemini, an offline fake and replay.
* :mod:`docfunnel.evals`: evaluations and regression gates for both stages.
* :mod:`docfunnel.datasets`: seeded synthetic datasets with exact ground truth.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("docfunnel")  # single source of truth: pyproject.toml
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"
