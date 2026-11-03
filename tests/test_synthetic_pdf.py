"""Multi-page synthetic PDFs: deterministic ground truth that matches what is rendered."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("reportlab")
pytest.importorskip("pypdfium2")
pytest.importorskip("numpy")

from docfunnel.cli import app
from docfunnel.evals.metrics import char_error_rate, normalize_whitespace
from docfunnel.parse import ParseOptions, parse_file
from docfunnel.schema import ReceiptExtraction
from docfunnel.synthetic_pdf import (
    DocTruth,
    generate_specs,
    generate_truths,
    load_manifest,
    manifest_sha256,
    render_pdf,
    write_pdf_dataset,
)
from docfunnel.validation import check_business_rules


@pytest.fixture(scope="module")
def truths() -> list[DocTruth]:
    return generate_truths()


def test_ground_truth_is_deterministic() -> None:
    first = [t.to_json() for t in generate_truths(n=6, seed=3)]
    assert first == [t.to_json() for t in generate_truths(n=6, seed=3)]
    assert first != [t.to_json() for t in generate_truths(n=6, seed=4)]


def test_default_set_covers_the_cases_the_parse_eval_needs(truths: list[DocTruth]) -> None:
    assert {t.doc_type for t in truths} == {"invoice", "contract"}
    assert {t.variant for t in truths} == {"digital", "scanned_light", "scanned_heavy", "mixed"}
    assert {t.locale for t in truths} == {"us", "uk", "de", "br"}
    pages = [p for t in truths for p in t.pages]
    assert 100 <= len(pages) <= 200  # small enough for CI
    assert Counter(p.noise for p in pages if p.scanned).keys() == {"light", "heavy"}
    assert any(p.background for p in pages)  # digital pages with a full-page image
    assert any(p.stray_text for p in pages)  # scans with a digital stamp
    assert max(len(t.pages) for t in truths) >= 4
    # Mixed documents contain both kinds of pages.
    for t in truths:
        if t.variant == "mixed":
            assert 0 < sum(p.scanned for p in t.pages) < len(t.pages) or len(t.pages) == 1


def test_field_spans_point_at_the_quote_on_the_gold_page(truths: list[DocTruth]) -> None:
    for t in truths:
        names = {f.name for f in t.fields}
        if t.doc_type == "invoice":
            assert {"vendor_name", "document_number", "date", "total"} <= names
        else:
            assert {"party_a", "effective_date", "governing_law", "notice_days"} <= names
        for f in t.fields:
            start, end = f.char_span
            printed = t.pages[f.page - 1].text[start:end]
            assert normalize_whitespace(printed) == f.quote, (t.id, f)


def test_invoice_totals_land_on_the_last_item_page_and_add_up(truths: list[DocTruth]) -> None:
    long_invoices = [t for t in truths if t.doc_type == "invoice" and len(t.pages) > 1]
    assert long_invoices
    for t in truths:
        if t.doc_type != "invoice":
            continue
        label = ReceiptExtraction.model_validate(
            {k: v for k, v in t.label.items() if k != "customer_name"}
        )
        assert not [i for i in check_business_rules(label) if i.severity == "error"], t.id
        total_page = next(f.page for f in t.fields if f.name == "total")
        assert total_page >= next(f.page for f in t.fields if f.name == "vendor_name")


def test_rendered_pdf_matches_ground_truth(tmp_path: Path) -> None:
    specs = list(generate_specs(n=12, seed=11))
    digital = next(s for s in specs if s.truth.variant == "digital" and len(s.truth.pages) > 1)
    scanned = next(s for s in specs if s.truth.variant.startswith("scanned_"))
    for spec in (digital, scanned):
        data = render_pdf(spec)
        assert data == render_pdf(spec)  # deterministic bytes
        path = tmp_path / spec.truth.file
        path.write_bytes(data)
        doc = parse_file(path, ParseOptions(ocr_engine="none"))
        assert len(doc.pages) == len(spec.truth.pages)
        for truth, page in zip(spec.truth.pages, doc.pages, strict=True):
            if truth.scanned:
                assert page.needs_ocr
                assert page.signals is not None
                assert page.signals.image_coverage == pytest.approx(1.0)
                assert page.text.strip() == (truth.stray_text or "")
            else:
                assert page.route == "text_layer"
                assert char_error_rate(truth.text, page.text) == 0.0


def test_write_and_load_dataset_via_cli(tmp_path: Path) -> None:
    out = tmp_path / "pdf"
    result = CliRunner().invoke(app, ["generate-pdfs", "--out", str(out), "--n", "3"])
    assert result.exit_code == 0, result.output
    assert "Wrote 3 documents" in result.output
    loaded = load_manifest(out)
    assert [t.to_json() for t in loaded] == [t.to_json() for t in generate_truths(n=3)]
    assert all((out / t.file).is_file() for t in loaded)
    digest = manifest_sha256(out)
    write_pdf_dataset(out, n=3)
    assert manifest_sha256(out) == digest
