"""Markdown export of a parsed document: pages, paragraphs, OCR notes, escaping."""

from __future__ import annotations

from pathlib import Path

import pytest

from docfunnel.parse import parse_file, to_markdown
from docfunnel.parse.markdown import escape_line, page_to_markdown, paragraphs
from docfunnel.parse.model import Block, Page, ParsedDocument, Route, Source


def make_page(
    rows: list[tuple[str, tuple[float, float, float, float] | None]],
    *,
    number: int = 1,
    source: Source = "text_layer",
    route: Route = "text_layer",
    text: str | None = None,
    **extra: object,
) -> Page:
    """A page whose text is the rows joined by newlines, unless ``text`` is given."""
    page_text = "\n".join(row for row, _ in rows) if text is None else text
    blocks, cursor = [], 0
    for index, (row, bbox) in enumerate(rows):
        start = page_text.index(row, cursor)
        cursor = start + len(row)
        blocks.append(
            Block(
                id=f"doc:p{number}:b{index}",
                page=number,
                text=row,
                bbox=bbox,
                char_span=(start, cursor),
                source=source,
            )
        )
    return Page.model_validate(
        {
            "number": number,
            "width": 595.0,
            "height": 842.0,
            "text": page_text,
            "route": route,
            "source": source,
            "blocks": blocks,
            **extra,
        }
    )


def box(y: float, x0: float = 50.0, x1: float = 300.0) -> tuple[float, float, float, float]:
    """A 9 pt high line box whose top edge is at ``y``."""
    return (x0, y, x1, y + 9.0)


def test_rows_on_a_regular_pitch_form_one_paragraph_and_a_gap_starts_another() -> None:
    page = make_page(
        [
            ("Riverside Garden Centre", box(100)),
            ("2 Quay Lane, Bristol", box(113)),
            ("VAT Reg No: GB 185 3708 72", box(126)),
            ("Invoice number: F-2023-85646", box(150)),  # a 24 pt step after 13 pt steps
            ("Invoice date: 20 Jul 2023", box(163)),
        ]
    )
    assert paragraphs(page) == [
        ["Riverside Garden Centre", "2 Quay Lane, Bristol", "VAT Reg No: GB 185 3708 72"],
        ["Invoice number: F-2023-85646", "Invoice date: 20 Jul 2023"],
    ]


def test_fragments_of_one_visual_row_are_joined_left_to_right() -> None:
    page = make_page(
        [
            ("Item Qty Unit Line total", box(100)),
            ("A4 Paper Ream #D298", box(113, 50, 150)),
            ("1 4.20 4.20", box(113.2, 300, 540)),  # same baseline band, to the right
            ("Desk Lamp #A319 12 24.00 288.00", box(126)),
        ]
    )
    assert paragraphs(page) == [
        [
            "Item Qty Unit Line total",
            "A4 Paper Ream #D298 1 4.20 4.20",
            "Desk Lamp #A319 12 24.00 288.00",
        ]
    ]


def test_overlapping_ocr_boxes_that_start_at_the_left_margin_stay_separate_rows() -> None:
    # OCR boxes are padded and overlap vertically, but each row starts at the margin.
    page = make_page(
        [
            ("Pint of Bitter #Z764 7 4.80 33.60", (59.6, 73.8, 552.3, 99.3)),
            ("A4 Paper Ream #Y059 4.20 4.20", (59.6, 87.0, 551.9, 112.0)),
        ],
        source="ocr",
        route="ocr:no_text",
    )
    assert paragraphs(page) == [
        ["Pint of Bitter #Z764 7 4.80 33.60", "A4 Paper Ream #Y059 4.20 4.20"]
    ]


def test_blocks_without_boxes_split_on_blank_lines() -> None:
    text = "MAPLE STREET HARDWARE\n910 Elm Rd\n\nTOTAL $72.08\n\n\nThank you!"
    page = make_page(
        [
            ("MAPLE STREET HARDWARE", None),
            ("910 Elm Rd", None),
            ("TOTAL $72.08", None),
            ("Thank you!", None),
        ],
        source="plain_text",
        route="plain_text",
        text=text,
    )
    assert paragraphs(page) == [
        ["MAPLE STREET HARDWARE", "910 Elm Rd"],
        ["TOTAL $72.08"],
        ["Thank you!"],
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# 924402", "\\# 924402"),
        ("#D298 Desk Lamp", "#D298 Desk Lamp"),  # not a heading: no space after '#'
        ("> quoted", "\\> quoted"),
        ("- item", "\\- item"),
        ("+ item", "\\+ item"),
        ("* item", "\\* item"),
        ("1. Definitions", "1\\. Definitions"),
        ("12) Notice", "12\\) Notice"),
        ("1.234,50 EUR", "1.234,50 EUR"),  # an amount, not a list item
        ("----------------", "\\----------------"),
        ("* * *", "\\* * *"),
        ("=====", "\\====="),
        ("Total 29.42", "Total 29.42"),
        ("-5.00 discount", "-5.00 discount"),
    ],
)
def test_escape_line_only_touches_block_markup(text: str, expected: str) -> None:
    assert escape_line(text) == expected


def test_ocr_pages_carry_a_note_with_engine_and_dpi() -> None:
    page = make_page(
        [("Terms and conditions", box(100))],
        number=2,
        source="ocr",
        route="ocr:scan_with_stray_text",
        ocr_engine="rapidocr@3.10.0",
        dpi=200,
    )
    assert page_to_markdown(page) == (
        "## Page 2\n\n"
        "> Text from OCR (rapidocr@3.10.0 at 200 dpi); it may contain recognition errors.\n\n"
        "Terms and conditions"
    )


def test_pages_without_text_or_with_errors_say_why() -> None:
    no_engine = make_page([], source="none", route="ocr:no_text")
    failed = make_page([], number=2, source="none", route="ocr:no_text", error="OCR timed out")
    assert page_to_markdown(no_engine) == (
        "## Page 1\n\n> No text: this page needs OCR, but no OCR engine was available."
    )
    assert page_to_markdown(failed) == "## Page 2\n\n> Page error: OCR timed out"


def test_document_has_a_title_and_one_section_per_page() -> None:
    document = ParsedDocument(
        doc_id="invoice",
        source_path="invoice.pdf",
        parser="test",
        pages=[
            make_page([("1. Services", box(100)), ("Fee 100.00", box(113))]),
            make_page([("Page two", box(100))], number=2),
        ],
    )
    assert to_markdown(document) == (
        "# invoice\n\n## Page 1\n\n1\\. Services\nFee 100.00\n\n## Page 2\n\nPage two\n"
    )


def test_text_file_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "receipt.txt"
    source.write_text("SHOP\n----\nTotal 3.00\n\nThanks\n", encoding="utf-8")
    markdown = to_markdown(parse_file(source))
    assert markdown == "# receipt\n\n## Page 1\n\nSHOP\n\\----\nTotal 3.00\n\nThanks\n"
