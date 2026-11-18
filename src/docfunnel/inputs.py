"""What the model is sent for a document: text, the file, or text with page images.

==============  =====================================================================
``text``        the parse stage's text: the text layer, OCR on scanned pages (default)
``hybrid``      text-layer pages as text, an image of each scanned page in its place
``hybrid-ocr``  ``hybrid``, plus each scanned page's OCR text after its image
``native``      the file itself (PDF or image)
==============  =====================================================================

On fully digital PDFs the three parsed routes send the same text. They differ only on
pages the parse stage sent to OCR. In the proof of concept (``docs/evaluation/
real-models.md``: GPT-6 Luna, 39 synthetic invoices, in-sample), ``hybrid-ocr`` did
best: the OCR text kept identifiers right and the image kept table rows right. Page
images need a model that reads images; ``native`` also needs one that reads PDFs (not
Ollama).
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from docfunnel.loaders import load_document, load_parsed
from docfunnel.parse.model import ParsedDocument
from docfunnel.parse.pipeline import (
    IMAGE_SUFFIXES,
    PDF_SUFFIXES,
    ParseOptions,
    UnsupportedDocumentError,
    parse_file,
)
from docfunnel.providers.base import Attachment

Route = Literal["text", "hybrid", "hybrid-ocr", "native"]
ROUTES: tuple[Route, ...] = get_args(Route)
DEFAULT_ROUTE: Route = "text"
DEFAULT_DPI = 150
"""Resolution of page images: small print stays legible at about 1,300 x 1,700 pixels."""

_SENT_AS_IS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_SENT_AS_IS |= {".webp": "image/webp", ".pdf": "application/pdf"}
# PDFium is not thread-safe; async callers run extractions in worker threads.
_PDFIUM_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ModelInput:
    """The prompt text and the files that go with it.

    A ``[[attachment:N]]`` marker in ``text`` puts file N at that point.
    """

    text: str
    attachments: tuple[Attachment, ...] = ()


def parse_route(value: str) -> Route:
    """``value`` as a :data:`Route`, or a ``ValueError`` naming the valid ones."""
    for route in ROUTES:
        if value == route:
            return route
    raise ValueError(f"unknown route {value!r}; expected one of {', '.join(ROUTES)}")


def build_input(
    path: Path,
    route: Route = DEFAULT_ROUTE,
    options: ParseOptions | None = None,
    *,
    dpi: int = DEFAULT_DPI,
) -> ModelInput:
    """What to send the model for the file at ``path`` on ``route``.

    Text files, and file types handled by a loader registered with
    :func:`docfunnel.loaders.register_loader`, are always sent as text.
    """
    suffix = path.suffix.lower()
    if route == "text" or suffix not in PDF_SUFFIXES | IMAGE_SUFFIXES:
        # Default options keep custom loaders registered for a suffix.
        text = load_document(path) if options is None else load_parsed(path, options)
        return ModelInput(text)
    if route == "native":
        return ModelInput("", (_file_attachment(path),))
    document = parse_file(path, options)
    model_input = page_image_input(document, path, dpi=dpi, with_ocr_text=route == "hybrid-ocr")
    if not model_input.text.strip() and not model_input.attachments:
        raise UnsupportedDocumentError(f"no text found in {path.name}")
    return model_input


def page_image_input(
    document: ParsedDocument,
    path: Path,
    *,
    dpi: int = DEFAULT_DPI,
    with_ocr_text: bool = False,
) -> ModelInput:
    """Text of the text-layer pages, and an image of each page the parse stage sent to OCR.

    Each image goes where its page was, between the text of the pages around it. With
    ``with_ocr_text``, the page's OCR text follows its image.
    """
    scanned = [page for page in document.pages if page.source == "ocr"]
    images = _page_images(path, [page.number for page in scanned], dpi) if scanned else {}
    parts: list[str] = []
    attachments: list[Attachment] = []
    for page in document.pages:
        if page.number not in images:
            parts.append(page.text)
            continue
        attachments.append(Attachment(images[page.number], "image/jpeg"))
        parts.append(f"[Page {page.number}, scanned:]\n[[attachment:{len(attachments)}]]")
        if with_ocr_text and page.text.strip():
            parts.append(f"[OCR text of page {page.number}, may contain errors:]\n{page.text}")
    return ModelInput("\n\n".join(part for part in parts if part), tuple(attachments))


def _page_images(path: Path, numbers: list[int], dpi: int) -> dict[int, bytes]:
    """JPEG of each listed page (1-based) of a PDF, or of an image file as page 1."""
    if path.suffix.lower() in IMAGE_SUFFIXES:
        from PIL import Image

        with Image.open(path) as image:
            return {1: _jpeg(image.convert("RGB"))} if 1 in numbers else {}
    import pypdfium2 as pdfium

    with _PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(str(path))
        try:
            return {
                n: _jpeg(pdf[n - 1].render(scale=dpi / 72, grayscale=True).to_pil())
                for n in numbers
            }
        finally:
            pdf.close()


def _jpeg(image: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)  # type: ignore[attr-defined]
    return buffer.getvalue()


def _file_attachment(path: Path) -> Attachment:
    suffix = path.suffix.lower()
    if suffix in _SENT_AS_IS:
        return Attachment(path.read_bytes(), _SENT_AS_IS[suffix])
    # TIFF, BMP: models take PNG, JPEG or WebP, so re-encode.
    from PIL import Image

    with Image.open(path) as image:
        return Attachment(_jpeg(image.convert("RGB")), "image/jpeg")
