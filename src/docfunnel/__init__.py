"""docfunnel: a proof of concept of parsing documents on the CPU before an LLM reads them.

Quick use::

    import docfunnel

    doc = docfunnel.parse_document("invoice.pdf")          # pages and blocks, no LLM
    result = docfunnel.extract_document("https://example.com/receipt.pdf")

Subpackages:

* :mod:`docfunnel.parse`: PDFs and scans to pages and blocks, OCR only where needed.
* :mod:`docfunnel.extract`: schema-validated LLM extraction with repair, fallback and
  review routing.
* :mod:`docfunnel.providers`: OpenAI, Anthropic, Gemini, Ollama, an offline fake and replay.
* :mod:`docfunnel.evals`: evaluations and regression gates for both stages.
* :mod:`docfunnel.datasets`: seeded synthetic datasets with exact ground truth.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

try:
    __version__ = version("docfunnel")  # single source of truth: pyproject.toml
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"

if TYPE_CHECKING:
    from docfunnel.library import (
        aextract_document,
        aparse_document,
        extract_document,
        parse_document,
    )
    from docfunnel.sources import FetchPolicy, SourceError

# Imported on first use, so `import docfunnel` (and every page-pool worker) stays light.
_LAZY = {
    "parse_document": "docfunnel.library",
    "extract_document": "docfunnel.library",
    "aparse_document": "docfunnel.library",
    "aextract_document": "docfunnel.library",
    "FetchPolicy": "docfunnel.sources",
    "SourceError": "docfunnel.sources",
}

__all__ = [
    "FetchPolicy",
    "SourceError",
    "__version__",
    "aextract_document",
    "aparse_document",
    "extract_document",
    "parse_document",
]


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        return getattr(import_module(_LAZY[name]), name)
    raise AttributeError(f"module 'docfunnel' has no attribute {name!r}")
