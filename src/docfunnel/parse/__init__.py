"""Fast CPU parsing stage: PDF text layer, per-page OCR decision, CPU OCR, page pool."""

from docfunnel.parse.model import PAGE_SEPARATOR, Block, Page, PageSignals, ParsedDocument
from docfunnel.parse.ocr import available_engines
from docfunnel.parse.pdf import OcrThresholds, decide_route
from docfunnel.parse.pipeline import (
    PagePool,
    ParseOptions,
    UnsupportedDocumentError,
    parse_documents,
    parse_file,
)

__all__ = [
    "PAGE_SEPARATOR",
    "Block",
    "OcrThresholds",
    "Page",
    "PagePool",
    "PageSignals",
    "ParseOptions",
    "ParsedDocument",
    "UnsupportedDocumentError",
    "available_engines",
    "decide_route",
    "parse_documents",
    "parse_file",
]
