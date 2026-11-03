"""Uniform parse output: ``ParsedDocument -> Page -> Block``.

Every parser (PDF text layer, OCR, plain text) produces the same structure, so the
stages after parsing (classification, chunking, retrieval, citations) never need to
know where the text came from. Offsets are the contract for later citations:

* ``Page.text`` is the full text of one page, lines separated by ``"\\n"``.
* ``Block.char_span`` is ``(start, end)`` into ``Page.text``, so
  ``page.text[start:end] == block.text`` always holds.
* ``ParsedDocument.text`` joins pages with :data:`PAGE_SEPARATOR`;
  :meth:`ParsedDocument.page_offsets` maps a page to its start in that string.

Coordinates (``bbox``) are PDF points with the origin at the **top-left** of the
page: ``(x0, y0, x1, y1)``. OCR boxes are converted from pixels to points so both
sources share one coordinate space.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

PAGE_SEPARATOR = "\n\n"

Source = Literal["text_layer", "ocr", "plain_text", "none"]
"""Where a page's text came from. ``none``: OCR was needed but no engine was available."""

Route = Literal[
    "text_layer",
    "plain_text",
    "ocr:no_text",
    "ocr:garbled",
    "ocr:scan_with_stray_text",
    "ocr:forced",
    "ocr:image",
]
"""The per-page decision. Every ``ocr:*`` value means the page was sent to OCR."""


class Block(BaseModel):
    """One unit of text on a page. Phase 1 emits one block per text line."""

    id: str = Field(description='Stable id "{doc_id}:p{page}:b{n}", what a citation points at.')
    page: int = Field(ge=1)
    kind: str = "line"
    text: str
    bbox: tuple[float, float, float, float] | None = None
    char_span: tuple[int, int]
    source: Source
    ocr_confidence: float | None = None


class PageSignals(BaseModel):
    """Cheap per-page measurements that drive the OCR decision."""

    alnum_chars: int
    text_chars: int
    bad_char_ratio: float = Field(description="U+FFFD and '(cid:' markers / text length")
    image_coverage: float = Field(description="Share of the page area covered by images (0-1)")


class Page(BaseModel):
    number: int = Field(ge=1)
    width: float
    height: float
    text: str
    route: Route
    source: Source
    blocks: list[Block] = Field(default_factory=list)
    signals: PageSignals | None = None
    ocr_engine: str | None = None
    dpi: int | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
    error: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def needs_ocr(self) -> bool:
        return self.route.startswith("ocr:")


class ParsedDocument(BaseModel):
    doc_id: str
    source_path: str
    parser: str = Field(description='Engines used, e.g. "pypdfium2@5.14.0+rapidocr@3.10.0"')
    pages: list[Page]
    timings_ms: dict[str, float] = Field(default_factory=dict)
    error: str | None = None

    @property
    def text(self) -> str:
        return PAGE_SEPARATOR.join(page.text for page in self.pages)

    @property
    def blocks(self) -> list[Block]:
        return [block for page in self.pages for block in page.blocks]

    def page_offsets(self) -> list[int]:
        """Start offset of each page inside :attr:`text` (index 0 is page 1)."""
        offsets, position = [], 0
        for page in self.pages:
            offsets.append(position)
            position += len(page.text) + len(PAGE_SEPARATOR)
        return offsets

    def locate(self, block: Block) -> tuple[int, int]:
        """Document-level ``(start, end)`` of a block inside :attr:`text`."""
        start = self.page_offsets()[block.page - 1]
        return start + block.char_span[0], start + block.char_span[1]
