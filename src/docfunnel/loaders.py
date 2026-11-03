"""Turn input files into text. OCR is pluggable and optional.

The extraction pipeline is text-in. Text files are read directly; PDFs use their
embedded text layer (``pypdf``, extra ``pdf``); images go through Tesseract
(``pytesseract`` + the ``tesseract`` binary, extra ``ocr``). Register another
backend (a cloud OCR, a layout model) with :func:`register_loader`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

Loader = Callable[[Path], str]


class UnsupportedDocumentError(ValueError):
    """No loader for this file type, or the optional dependency is missing."""


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise UnsupportedDocumentError("PDF input requires the 'pdf' extra (pypdf)") from exc
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages).strip()
    if not text:
        raise UnsupportedDocumentError(
            f"{path.name} has no text layer; rasterize it and use an OCR loader"
        )
    return text


def load_image(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise UnsupportedDocumentError(
            "image input requires the 'ocr' extra and the tesseract binary"
        ) from exc
    with Image.open(path) as image:
        return pytesseract.image_to_string(image)


_LOADERS: dict[str, Loader] = {
    ".txt": load_text_file,
    ".md": load_text_file,
    ".pdf": load_pdf,
    **dict.fromkeys((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"), load_image),
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
