"""What the model is sent on each route, for PDFs, images and text files."""

from __future__ import annotations

from pathlib import Path

import pytest

from docfunnel import extract_document
from docfunnel.extract.extractor import Extractor, ModelTarget, RetryPolicy
from docfunnel.inputs import build_input, page_image_input, parse_route
from docfunnel.parse import parse_file

from helpers import ScriptedProvider

pytest.importorskip("pypdfium2")
pytest.importorskip("PIL")

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
MIXED = EXAMPLES / "invoice_mixed_scan.pdf"


def test_hybrid_ocr_puts_the_ocr_text_after_each_scanned_page_image() -> None:
    parsed = parse_file(MIXED)
    scanned = [p for p in parsed.pages if p.source == "ocr"]
    assert scanned
    plain = page_image_input(parsed, MIXED, dpi=72)
    both = page_image_input(parsed, MIXED, dpi=72, with_ocr_text=True)
    assert len(plain.attachments) == len(both.attachments) == len(scanned)
    assert all(a.data.startswith(b"\xff\xd8") for a in both.attachments)  # JPEG
    assert "OCR text of page" not in plain.text
    number = scanned[0].number
    assert both.text.index(f"[Page {number}, scanned:]") < both.text.index(
        f"[OCR text of page {number}"
    )
    digital = next(p for p in parsed.pages if p.source != "ocr")
    assert digital.text.strip()[:40] in plain.text


def test_routes_for_each_file_type(tmp_path: Path) -> None:
    text = build_input(MIXED, "text")
    assert text.attachments == ()
    assert text.text
    native = build_input(MIXED, "native")
    assert native.text == ""
    assert native.attachments[0].media_type == "application/pdf"
    note = tmp_path / "note.txt"
    note.write_text("Total: 12.00 USD")
    assert build_input(note, "hybrid-ocr").text == "Total: 12.00 USD"  # text files stay text

    from PIL import Image

    tiff = tmp_path / "scan.tiff"
    Image.new("RGB", (40, 20), "white").save(tiff)
    assert build_input(tiff, "native").attachments[0].media_type == "image/jpeg"
    with pytest.raises(ValueError, match="expected one of text, hybrid, hybrid-ocr, native"):
        parse_route("vision")


def test_extract_document_sends_page_images_on_the_hybrid_ocr_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = '{"total": 1, "currency": "USD", "line_items": []}'
    scripted = ScriptedProvider([answer, answer])
    extractor = Extractor([ModelTarget(scripted, "m")], retry=RetryPolicy(max_attempts=1))

    extract_document(MIXED, extractor=extractor, route="hybrid-ocr")
    assert scripted.requests[0].attachments
    assert "[OCR text of page" in scripted.requests[0].messages[1].content

    monkeypatch.setenv("DOCFUNNEL_ROUTE", "text")
    extract_document(MIXED, extractor=extractor)
    assert not scripted.requests[1].attachments
