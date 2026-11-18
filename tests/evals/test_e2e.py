"""End-to-end evaluation: set building, both routes, budget cap and report, offline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docfunnel.evals.e2e import (
    E2EConfig,
    build_e2e_set,
    load_e2e_report,
    load_e2e_set,
    run_e2e,
    write_e2e_report,
)
from docfunnel.extract.extractor import Extractor, ModelTarget, RetryPolicy
from docfunnel.extract.pricing import PriceTable
from docfunnel.extract.prompts import ATTACHED_DOCUMENT_PROMPT

from helpers import ScriptedProvider

pytest.importorskip("reportlab")
pytest.importorskip("pypdfium2")


@pytest.fixture(scope="module")
def e2e_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from docfunnel.datasets.pdfs import write_pdf_dataset

    pdfs = tmp_path_factory.mktemp("pdfs")
    write_pdf_dataset(pdfs, n=12, seed=11)
    out = tmp_path_factory.mktemp("e2e")
    build_e2e_set(pdfs, out, n_large=2, seed=5)
    return out


def test_set_has_small_invoices_and_large_merged_ones(e2e_dir: Path) -> None:
    docs = load_e2e_set(e2e_dir)
    small = [d for d in docs if d.size == "small"]
    large = [d for d in docs if d.size == "large"]
    assert small
    assert len(large) == 2
    import pypdfium2 as pdfium

    for doc in large:
        pdf = pdfium.PdfDocument(str(e2e_dir / doc.file))
        assert len(pdf) == doc.pages > max(d.pages for d in small)
        pdf.close()
    assert all(d.label.total is not None for d in docs)
    raw = json.loads((e2e_dir / "e2e.jsonl").read_text().splitlines()[0])
    assert "customer_name" not in raw["label"]  # generator distractor, not a schema field


def _answer(total: float) -> str:
    return json.dumps({"total": total, "currency": "USD", "line_items": []})


def test_both_routes_budget_and_report(e2e_dir: Path, tmp_path: Path) -> None:
    docs = load_e2e_set(e2e_dir)[:3]
    providers: list[ScriptedProvider] = []

    def make(provider: str, model: str, config: E2EConfig) -> Extractor:
        scripted = ScriptedProvider([_answer(float(d.label.total or 0)) for d in docs] * 2)
        providers.append(scripted)
        prices = PriceTable.from_mapping({model: {"input": 1000.0, "output": 0.0}})
        return Extractor(
            [ModelTarget(scripted, model)], retry=RetryPolicy(max_attempts=1), prices=prices
        )

    config = E2EConfig(
        dataset=e2e_dir,
        targets=[("scripted", "cheap-model")],
        limit=3,
        workers=1,
        default_budget_usd=3.5,  # 1,000 input tokens at $1,000/M = $1 per call
    )
    report = run_e2e(config, make_extractor=make)

    requests = providers[0].requests
    text_requests = [r for r in requests if not r.attachments]
    file_requests = [r for r in requests if r.attachments]
    assert len(text_requests) == 3  # text route: parsed text, no file
    assert "<document>" in text_requests[0].messages[1].content
    # Budget: $3 spent after the text route, so one native call runs, two are skipped.
    assert len(file_requests) == 1
    assert file_requests[0].attachments[0].media_type == "application/pdf"
    assert file_requests[0].messages[1].content == ATTACHED_DOCUMENT_PROMPT
    assert report.meta.skipped_calls == 2
    assert report.meta.spent_usd == {"scripted": 4.0}

    by_route = {g.route: g.metrics for g in report.groups if g.slice == "all"}
    assert by_route["text"].documents == 3
    assert by_route["native"].documents == 1
    assert by_route["text"].field_accuracy > 0

    json_path, md_path = write_e2e_report(report, tmp_path)
    assert load_e2e_report(json_path).meta == report.meta
    markdown = md_path.read_text()
    assert "| `cheap-model` | text | 3 |" in markdown
    assert "### Against the text route" in markdown
    assert "skipped calls (budget reached or provider stopped): 2" in markdown


def test_hybrid_sends_images_of_scanned_pages_and_reuses_digital_results(
    e2e_dir: Path,
) -> None:
    docs = load_e2e_set(e2e_dir)
    scripted = ScriptedProvider([_answer(float(d.label.total or 0)) for d in docs] * 2)

    def make(provider: str, model: str, config: E2EConfig) -> Extractor:
        prices = PriceTable.from_mapping({model: {"input": 0.0, "output": 0.0}})
        return Extractor(
            [ModelTarget(scripted, model)], retry=RetryPolicy(max_attempts=1), prices=prices
        )

    config = E2EConfig(
        dataset=e2e_dir,
        targets=[("scripted", "m")],
        routes=("hybrid", "text"),  # run in text-first order regardless
        workers=4,  # page images are rendered before the threads start (PDFium)
    )
    report = run_e2e(config, make_extractor=make)

    hybrid = [r for r in report.rows if r.route == "hybrid"]
    reused = [r for r in hybrid if r.reused]
    image_requests = [r for r in scripted.requests if r.attachments]
    # A document is reused when the parse stage sent none of its pages to OCR, which can
    # differ from the scanned label (a digital page on a letterhead image goes to OCR).
    assert image_requests
    assert len(reused) + len(image_requests) == len(hybrid) == len(docs)
    assert all(d.scanned_pages == 0 for d in docs if d.id in {r.doc_id for r in reused})
    for request in image_requests:
        assert all(a.media_type == "image/jpeg" for a in request.attachments)
        assert all(a.data.startswith(b"\xff\xd8") for a in request.attachments)
        assert "[[attachment:1]]" in request.messages[1].content
    assert report.meta.routes == ["text", "hybrid"]


def test_a_provider_that_fails_without_tokens_is_stopped(e2e_dir: Path) -> None:
    from docfunnel.providers.base import ProviderError

    error = ProviderError("402 RESOURCE_EXHAUSTED: credits are depleted", retryable=False)
    scripted = ScriptedProvider([error] * 50)

    def make(provider: str, model: str, config: E2EConfig) -> Extractor:
        return Extractor([ModelTarget(scripted, model)], retry=RetryPolicy(max_attempts=1))

    config = E2EConfig(
        dataset=e2e_dir, targets=[("broke", "m")], routes=("native",), workers=1, limit=6
    )
    report = run_e2e(config, make_extractor=make)

    assert len(scripted.requests) == 3  # DEAD_CALLS_LIMIT, then the provider is stopped
    assert [r.skip_reason for r in report.rows if r.skipped] == ["provider_unavailable"] * 3
    assert "credits are depleted" in report.meta.unavailable["broke"]
