"""Parse stage: text layer, OCR routing, OCR engines, page pool, offsets."""

from __future__ import annotations

import io
import math
from pathlib import Path

import pytest

from docfunnel.evals.metrics import char_error_rate
from docfunnel.parse import (
    PageSignals,
    ParseOptions,
    UnsupportedDocumentError,
    decide_route,
    parse_documents,
    parse_file,
)
from docfunnel.parse.model import PAGE_SEPARATOR
from docfunnel.parse.ocr import (
    OcrLine,
    assemble_rows,
    available_engines,
    lines_to_blocks,
    resolve_engine_name,
)
from docfunnel.parse.pdf import OcrThresholds

pytest.importorskip("pypdfium2")
reportlab = pytest.importorskip("reportlab")

LINES = [
    "INVOICE INV-2024-00042",
    "Bäckerei Sonnenschein GmbH - USt-IdNr.: DE123456789",
    "Beratung (Std.) 3 95,00 285,00",
    "Total due 1.234,50 € - Paid by bank transfer",
]
HAS_OCR = bool(available_engines())


def _draw_lines(canvas, lines: list[str], size: float = 12) -> None:
    y = 760.0
    for line in lines:
        canvas.setFont("Helvetica", size)
        canvas.drawString(60, y, line)
        y -= size * 1.6


def make_text_pdf(path: Path, pages: list[list[str]]) -> Path:
    from reportlab.pdfgen.canvas import Canvas

    canvas = Canvas(str(path), invariant=1)
    for lines in pages:
        _draw_lines(canvas, lines)
        canvas.showPage()
    canvas.save()
    return path


def make_scanned_pdf(path: Path, lines: list[str], stray: str | None = None) -> Path:
    """Render a digital page to an image and rebuild it as an image-only page."""
    import pypdfium2 as pdfium
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas

    digital = make_text_pdf(path.with_suffix(".digital.pdf"), [lines])
    image = pdfium.PdfDocument(str(digital))[0].render(scale=200 / 72).to_pil()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    canvas = Canvas(str(path), invariant=1)
    width, height = canvas._pagesize
    canvas.drawImage(ImageReader(io.BytesIO(buffer.getvalue())), 0, 0, width, height)
    if stray:
        canvas.setFont("Helvetica", 6)
        canvas.drawString(40, 14, stray)
    canvas.showPage()
    canvas.save()
    return path


# ---- routing -----------------------------------------------------------------------


def signals(alnum: int, coverage: float = 0.0, bad: float = 0.0) -> PageSignals:
    return PageSignals(
        alnum_chars=alnum, text_chars=alnum, bad_char_ratio=bad, image_coverage=coverage
    )


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (signals(500), "text_layer"),
        (signals(0, coverage=1.0), "ocr:no_text"),
        (signals(39), "ocr:no_text"),
        (signals(500, bad=0.2), "ocr:garbled"),
        (signals(120, coverage=0.95), "ocr:scan_with_stray_text"),
        (signals(800, coverage=0.95), "text_layer"),  # letterhead image under real text
    ],
)
def test_decide_route(page: PageSignals, expected: str) -> None:
    assert decide_route(page) == expected


def test_force_ocr_and_custom_thresholds() -> None:
    assert decide_route(signals(500), force_ocr=True) == "ocr:forced"
    assert decide_route(signals(60), OcrThresholds(min_chars=100)) == "ocr:no_text"


# ---- text layer ----------------------------------------------------------------------


def test_text_layer_pages_blocks_and_offsets(tmp_path: Path) -> None:
    pdf = make_text_pdf(tmp_path / "doc.pdf", [LINES, ["Page two", "Second page text here"]])
    doc = parse_file(pdf, ParseOptions(ocr_engine="none"))
    assert doc.parser.startswith("pypdfium2@")
    assert [p.number for p in doc.pages] == [1, 2]
    first = doc.pages[0]
    assert first.route == "text_layer"
    assert first.source == "text_layer"
    assert not first.needs_ocr
    assert first.text.split("\n") == LINES
    assert [b.text for b in first.blocks] == LINES
    for page in doc.pages:
        for block in page.blocks:
            start, end = block.char_span
            assert page.text[start:end] == block.text
            assert block.id.startswith(f"doc:p{page.number}:b")
            x0, y0, x1, y1 = block.bbox
            assert 0 <= x0 < x1 <= page.width
            assert 0 <= y0 < y1 <= page.height
    # Top-left origin: lines further down the page have larger y.
    assert first.blocks[0].bbox[1] < first.blocks[-1].bbox[1]
    # Document-level offsets.
    assert doc.text == PAGE_SEPARATOR.join(p.text for p in doc.pages)
    last = doc.pages[1].blocks[-1]
    start, end = doc.locate(last)
    assert doc.text[start:end] == last.text


def test_page_without_text_and_without_ocr_is_flagged(tmp_path: Path) -> None:
    pdf = make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    page = parse_file(pdf, ParseOptions(ocr_engine="none")).pages[0]
    assert page.route == "ocr:no_text"
    assert page.source == "none"
    assert page.signals is not None
    assert page.signals.image_coverage == pytest.approx(1.0)
    assert page.error
    assert "no OCR engine" in page.error


def test_stray_text_without_ocr_keeps_the_text_layer(tmp_path: Path) -> None:
    stray = "Scanned by OfficeScan 4000 on 2024-03-05 14:22 - batch 0042 - page 1"
    pdf = make_scanned_pdf(tmp_path / "scan.pdf", LINES, stray=stray)
    page = parse_file(pdf, ParseOptions(ocr_engine="none")).pages[0]
    assert page.route == "ocr:scan_with_stray_text"
    assert page.source == "text_layer"
    assert page.text == stray


def test_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "x.docx"
    path.write_text("x")
    with pytest.raises(UnsupportedDocumentError):
        parse_file(path)


def test_plain_text_file(tmp_path: Path) -> None:
    path = tmp_path / "r.txt"
    path.write_text("  first line\n\nsecond line\n")
    doc = parse_file(path)
    page = doc.pages[0]
    assert page.route == "plain_text"
    assert [b.text for b in page.blocks] == ["first line", "second line"]
    for block in page.blocks:
        assert page.text[block.char_span[0] : block.char_span[1]] == block.text


# ---- OCR ---------------------------------------------------------------------------


def test_resolve_engine_name() -> None:
    assert resolve_engine_name("none") is None
    assert resolve_engine_name("auto") in {*available_engines(), None}
    with pytest.raises(ValueError, match="unknown OCR engine"):
        resolve_engine_name("nope")


def _line(text: str, x0: float, y: float, width: float, angle: float = 0.0) -> OcrLine:
    return OcrLine(
        text=text,
        box=(
            x0,
            y - 10 + x0 * math.tan(angle),
            x0 + width,
            y + 10 + (x0 + width) * math.tan(angle),
        ),
        height=20,
        confidence=0.9,
        angle=angle,
    )


def test_rows_are_grouped_across_columns_on_a_skewed_page() -> None:
    angle = math.radians(2.0)  # the right column drifts ~35 px over 1000 px
    lines = [
        _line("Total", 900, 300, 100, angle),
        _line("Item A", 50, 100, 400, angle),
        _line("12,00", 900, 100, 100, angle),
        _line("Item B", 50, 140, 400, angle),
        _line("3,50", 900, 140, 100, angle),
        _line("Subtotal", 50, 300, 400, angle),
    ]
    rows = [[item.text for item in row] for row in assemble_rows(lines)]
    assert rows == [["Item A", "12,00"], ["Item B", "3,50"], ["Subtotal", "Total"]]


def test_lines_to_blocks_converts_pixels_to_points() -> None:
    lines = [_line("hello", 0, 100, 144), _line("world", 0, 200, 144)]
    text, blocks = lines_to_blocks(lines, doc_id="d", page_number=3, scale=2.0)
    assert text == "hello\nworld"
    assert [b.id for b in blocks] == ["d:p3:b0", "d:p3:b1"]
    assert blocks[0].bbox == (0.0, 45.0, 72.0, 55.0)
    assert blocks[1].char_span == (6, 11)
    assert blocks[0].source == "ocr"
    assert blocks[0].ocr_confidence == 0.9


@pytest.mark.skipif("rapidocr" not in available_engines(), reason="RapidOCR not installed")
def test_rapidocr_reads_a_scanned_page(tmp_path: Path) -> None:
    pdf = make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    page = parse_file(pdf, ParseOptions(ocr_engine="rapidocr")).pages[0]
    assert page.route == "ocr:no_text"
    assert page.source == "ocr"
    assert page.ocr_engine
    assert page.ocr_engine.startswith("rapidocr@")
    assert char_error_rate("\n".join(LINES), page.text) < 0.05
    assert all(b.source == "ocr" and b.bbox for b in page.blocks)


@pytest.mark.skipif("tesseract" not in available_engines(), reason="Tesseract not installed")
def test_tesseract_reads_a_scanned_page(tmp_path: Path) -> None:
    pdf = make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    page = parse_file(pdf, ParseOptions(ocr_engine="tesseract")).pages[0]
    assert page.source == "ocr"
    assert page.ocr_engine
    assert page.ocr_engine.startswith("tesseract@")
    # The default 'eng' model drops diacritics (ä, €), so allow a few edits.
    assert char_error_rate("\n".join(LINES), page.text) < 0.10


@pytest.mark.skipif(not HAS_OCR, reason="no OCR engine installed")
def test_force_ocr_on_a_digital_page(tmp_path: Path) -> None:
    pdf = make_text_pdf(tmp_path / "doc.pdf", [LINES])
    page = parse_file(pdf, ParseOptions(force_ocr=True)).pages[0]
    assert page.route == "ocr:forced"
    assert page.source == "ocr"
    assert "render" in page.timings_ms
    assert "ocr" in page.timings_ms


def test_ocr_failure_is_isolated_to_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from docfunnel.parse import pipeline

    class Boom:
        name, version = "boom", "0"

        def recognize(self, image: object) -> list[OcrLine]:
            raise RuntimeError("model crashed")

    monkeypatch.setattr(pipeline, "_engine_for", lambda options: Boom())
    pdf = make_text_pdf(tmp_path / "doc.pdf", [LINES, LINES])
    doc = parse_file(pdf, ParseOptions(force_ocr=True))
    assert len(doc.pages) == 2
    assert all(p.error == "RuntimeError: model crashed" for p in doc.pages)


# ---- process pool ------------------------------------------------------------------


def test_page_pool_matches_sequential_parsing(tmp_path: Path) -> None:
    paths = [
        make_text_pdf(tmp_path / "a.pdf", [LINES, ["second page of a", "more text on it"]]),
        make_scanned_pdf(tmp_path / "b.pdf", LINES),
        make_text_pdf(tmp_path / "c.pdf", [["only page of c", "with a few words"]]),
    ]
    text_file = tmp_path / "d.txt"
    text_file.write_text("plain text document")
    paths.append(text_file)
    options = ParseOptions(ocr_engine="none")
    sequential = parse_documents(paths, options, workers=1)
    pooled = parse_documents(paths, options, workers=2)
    assert [d.doc_id for d in pooled] == ["a", "b", "c", "d"]
    assert [d.text for d in pooled] == [d.text for d in sequential]
    assert [p.route for d in pooled for p in d.pages] == [
        p.route for d in sequential for p in d.pages
    ]


def test_page_pool_reports_unreadable_files(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    good = make_text_pdf(tmp_path / "good.pdf", [LINES])
    docs = parse_documents([broken, good], ParseOptions(ocr_engine="none"), workers=2)
    assert docs[0].error
    assert not docs[0].pages
    assert docs[1].pages[0].text.split("\n") == LINES
