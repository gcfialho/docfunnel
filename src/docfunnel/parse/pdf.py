"""PDF text layer and the per-page OCR decision, both on ``pypdfium2`` (extra ``pdf``).

``pypdfium2`` wraps PDFium (the PDF engine in Chrome). It gives the text layer with
character boxes and renders pages to images, with no Python-level parsing, which is
why it is much faster than ``pypdf``. PDFium is **not thread-safe**: parallelism
happens in processes (see :mod:`docfunnel.parse.pipeline`).

The OCR decision is made per page, never per file, because real PDFs are often
mixed (a scanned annex at the end of a digital invoice).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from docfunnel.parse.model import Block, PageSignals, Route

if TYPE_CHECKING:  # pragma: no cover
    import pypdfium2 as pdfium


class MissingDependencyError(ImportError):
    """An optional dependency for this parse path is not installed."""


def require_pdfium() -> Any:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise MissingDependencyError("PDF input requires the 'pdf' extra (pypdfium2)") from exc
    return pdfium


def pdfium_version() -> str:
    pdfium = require_pdfium()
    return str(pdfium.version.PYPDFIUM_INFO).split("+")[0].removeprefix("v")


@dataclass(frozen=True)
class OcrThresholds:
    """Heuristic thresholds for :func:`decide_route` (defaults from the design notes).

    Similar libraries use the same order of magnitude: ~40 glyphs and 50% image
    coverage (``pdf-engine``), 50 chars or >80% coverage (``pdf_oxide``). They are
    measured, not trusted: the parse eval reports routing precision and recall on
    the synthetic set, where every page is labelled scanned or digital.
    """

    min_chars: int = 40
    scan_cover: float = 0.5
    max_stray_chars: int = 200
    max_bad_ratio: float = 0.05


def decide_route(
    signals: PageSignals, thresholds: OcrThresholds | None = None, *, force_ocr: bool = False
) -> Route:
    t = thresholds or OcrThresholds()
    if force_ocr:
        return "ocr:forced"
    if signals.alnum_chars < t.min_chars:
        return "ocr:no_text"  # no (useful) text layer
    if signals.bad_char_ratio > t.max_bad_ratio:
        return "ocr:garbled"  # font without a ToUnicode map, broken encoding
    if signals.image_coverage > t.scan_cover and signals.alnum_chars < t.max_stray_chars:
        return "ocr:scan_with_stray_text"  # a scan with a digital stamp or footer
    return "text_layer"


def image_coverage(page: pdfium.PdfPage) -> float:
    """Share of the page covered by image objects (overlaps are not subtracted)."""
    import pypdfium2.raw as pdfium_c

    width, height = page.get_size()
    area = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
        left, bottom, right, top = obj.get_bounds()
        left, right = max(0.0, left), min(width, right)
        bottom, top = max(0.0, bottom), min(height, top)
        area += max(0.0, right - left) * max(0.0, top - bottom)
    return min(area / (width * height), 1.0) if width and height else 0.0


def page_signals(raw_text: str, page: pdfium.PdfPage) -> PageSignals:
    bad = raw_text.count("�") + raw_text.count("(cid:")
    return PageSignals(
        alnum_chars=sum(ch.isalnum() for ch in raw_text),
        text_chars=len(raw_text),
        bad_char_ratio=round(bad / max(len(raw_text), 1), 4),
        image_coverage=round(image_coverage(page), 4),
    )


def _split_raw_lines(raw: str) -> list[tuple[int, str]]:
    """Split PDFium text into ``(raw_start_index, line)``; PDFium emits ``\\r\\n``."""
    lines: list[tuple[int, str]] = []
    start = 0
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch in "\r\n":
            lines.append((start, raw[start:i]))
            if ch == "\r" and i + 1 < len(raw) and raw[i + 1] == "\n":
                i += 1
            start = i + 1
        i += 1
    lines.append((start, raw[start:]))
    return lines


def text_layer_blocks(
    textpage: pdfium.PdfTextPage,
    raw: str,
    *,
    doc_id: str,
    page_number: int,
    page_height: float,
    with_boxes: bool = True,
) -> tuple[str, list[Block]]:
    """Normalize the text layer to ``\\n`` line breaks and cut it into line blocks.

    PDFium's character indices line up with the string returned by
    ``get_text_range`` (one index per UTF-16 code unit), so the raw index of a line
    can be used to ask PDFium for the rectangles covering it.
    """
    lines = _split_raw_lines(raw)
    text = "\n".join(line for _, line in lines)
    blocks: list[Block] = []
    offset = 0
    for raw_start, line in lines:
        stripped = line.strip()
        if stripped:
            lead = len(line) - len(line.lstrip())
            start = offset + lead
            bbox = None
            if with_boxes:
                bbox = _line_bbox(textpage, raw_start + lead, len(stripped), page_height)
            blocks.append(
                Block(
                    id=f"{doc_id}:p{page_number}:b{len(blocks)}",
                    page=page_number,
                    text=stripped,
                    bbox=bbox,
                    char_span=(start, start + len(stripped)),
                    source="text_layer",
                )
            )
        offset += len(line) + 1
    return text, blocks


def _line_bbox(
    textpage: pdfium.PdfTextPage, index: int, count: int, page_height: float
) -> tuple[float, float, float, float] | None:
    n_rects = textpage.count_rects(index, count)
    if n_rects <= 0:
        return None
    lefts, bottoms, rights, tops = zip(*(textpage.get_rect(i) for i in range(n_rects)), strict=True)
    return (
        round(min(lefts), 2),
        round(page_height - max(tops), 2),
        round(max(rights), 2),
        round(page_height - min(bottoms), 2),
    )


def render_page(page: pdfium.PdfPage, dpi: int) -> Any:
    """Render a page to a greyscale PIL image (OCR engines do not need colour)."""
    return page.render(scale=dpi / 72, grayscale=True).to_pil()
