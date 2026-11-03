"""Turn input files into text for the extraction step.

Built-in file types go through the parse stage (:mod:`docfunnel.parse`): text files
are read directly, PDFs use the ``pypdfium2`` text layer with OCR only on the pages
that need it, and images go to the installed OCR engine (RapidOCR, else Tesseract).
Use :func:`docfunnel.parse.parse_file` directly when you need pages, blocks and
offsets instead of a flat string. Register another backend (a cloud OCR, a layout
model) for a suffix with :func:`register_loader`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docfunnel.parse.pipeline import (
    IMAGE_SUFFIXES,
    PDF_SUFFIXES,
    TEXT_SUFFIXES,
    ParseOptions,
    UnsupportedDocumentError,
    parse_file,
)

Loader = Callable[[Path], str]

__all__ = [
    "Loader",
    "UnsupportedDocumentError",
    "load_document",
    "register_loader",
    "supported_suffixes",
]


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_parsed(path: Path, options: ParseOptions | None = None) -> str:
    document = parse_file(path, options)
    text = document.text.strip()
    if not text:
        missing_ocr = any(page.source == "none" for page in document.pages)
        hint = "; install the 'ocr' extra to OCR scanned pages" if missing_ocr else ""
        raise UnsupportedDocumentError(f"no text found in {path.name}{hint}")
    return text


_LOADERS: dict[str, Loader] = {
    **dict.fromkeys(TEXT_SUFFIXES, load_text_file),
    **dict.fromkeys(PDF_SUFFIXES | IMAGE_SUFFIXES, load_parsed),
}


def register_loader(suffix: str, loader: Loader) -> None:
    _LOADERS[suffix.lower()] = loader


def supported_suffixes() -> list[str]:
    return sorted(_LOADERS)


def load_document(path: Path) -> str:
    loader = _LOADERS.get(path.suffix.lower())
    if loader is None:
        raise UnsupportedDocumentError(
            f"unsupported file type {path.suffix!r}; supported: {', '.join(supported_suffixes())}"
        )
    return loader(path)
