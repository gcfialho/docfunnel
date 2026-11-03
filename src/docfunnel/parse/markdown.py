"""Render a :class:`ParsedDocument` as Markdown, one ``## Page N`` section per page.

Blocks are text lines in reading order. They are turned into paragraphs like this:

* Fragments of one visual row (a text-layer description and its amounts, drawn as
  separate runs) are joined with a space when their boxes share a baseline band and
  the second starts to the right of the first.
* A new paragraph starts where the vertical step between two rows is clearly larger
  than the page's usual line pitch. Blocks without boxes (plain text) split on blank
  lines in the page text instead.
* Lines inside a paragraph stay on separate source lines (soft breaks), so table rows
  keep their shape for a downstream LLM; Markdown renderers still reflow them.

Text is not otherwise rewritten. Only line starts that Markdown would read as a
heading, quote, list item, rule or heading underline are escaped, so the output stays plain text.
"""

from __future__ import annotations

import re
from itertools import pairwise
from statistics import median

from docfunnel.parse.model import Block, Page, ParsedDocument

PARAGRAPH_GAP = 1.6
"""A row step above this multiple of the page's median line pitch starts a paragraph."""

SAME_ROW_OFFSET = 0.3
"""Boxes are one row when their centres differ by less than this share of the lower height."""

_BLOCK_MARKUP = re.compile(
    r"^(#{1,6}(?=\s|$)|>|[-+*](?=\s|$)|\d{1,9}[.)](?=\s|$)|([-*_])\s*\2\s*\2|=+\s*$)"
)


def escape_line(text: str) -> str:
    """Backslash-escape a line start that Markdown would parse as block markup."""
    match = _BLOCK_MARKUP.match(text)
    if match is None:
        return text
    marker = match.group(1)
    if marker[0].isdigit():  # "1." -> "1\." keeps the number readable
        cut = len(marker) - 1
        return text[:cut] + "\\" + text[cut:]
    return "\\" + text


def _same_row(previous: Block, block: Block) -> bool:
    if previous.bbox is None or block.bbox is None:
        return False
    _, py0, px1, py1 = previous.bbox
    x0, y0, _, y1 = block.bbox
    height = min(py1 - py0, y1 - y0)
    if height <= 0 or x0 <= px1:
        return False
    return abs((py0 + py1) / 2 - (y0 + y1) / 2) < SAME_ROW_OFFSET * height


def _rows(blocks: list[Block]) -> list[list[Block]]:
    rows: list[list[Block]] = []
    for block in blocks:
        if rows and _same_row(rows[-1][-1], block):
            rows[-1].append(block)
        else:
            rows.append([block])
    return rows


def _centre(row: list[Block]) -> float | None:
    boxes = [b.bbox for b in row if b.bbox is not None]
    if not boxes:
        return None
    return sum((box[1] + box[3]) / 2 for box in boxes) / len(boxes)


def paragraphs(page: Page) -> list[list[str]]:
    """Group a page's blocks into paragraphs of lines, in reading order."""
    rows = _rows([b for b in page.blocks if b.text.strip()])
    if not rows:
        return []
    centres = [_centre(row) for row in rows]
    steps = [b - a for a, b in pairwise(centres) if a is not None and b is not None and b > a]
    pitch = median(steps) if steps else None

    groups: list[list[str]] = []
    for index, row in enumerate(rows):
        line = " ".join(block.text.strip() for block in row)
        if index == 0:
            groups.append([line])
            continue
        before, here = centres[index - 1], centres[index]
        if pitch is not None and before is not None and here is not None:
            new_paragraph = here - before > PARAGRAPH_GAP * pitch
        else:
            # No boxes (plain text): a blank line between the blocks ends a paragraph.
            gap = page.text[rows[index - 1][-1].char_span[1] : row[0].char_span[0]]
            new_paragraph = gap.count("\n") >= 2
        if new_paragraph:
            groups.append([line])
        else:
            groups[-1].append(line)
    return groups


def _page_note(page: Page) -> str | None:
    if page.error:
        return f"> Page error: {page.error}"
    if page.source == "none":
        return "> No text: this page needs OCR, but no OCR engine was available."
    if page.source == "ocr":
        engine = page.ocr_engine or "OCR"
        dpi = f" at {page.dpi} dpi" if page.dpi else ""
        return f"> Text from OCR ({engine}{dpi}); it may contain recognition errors."
    return None


def page_to_markdown(page: Page) -> str:
    parts = [f"## Page {page.number}"]
    note = _page_note(page)
    if note:
        parts.append(note)
    parts.extend("\n".join(escape_line(line) for line in group) for group in paragraphs(page))
    return "\n\n".join(parts)


def to_markdown(document: ParsedDocument) -> str:
    """The whole document as Markdown: a title, then one section per page."""
    sections = [f"# {document.doc_id}", *(page_to_markdown(page) for page in document.pages)]
    return "\n\n".join(sections) + "\n"
