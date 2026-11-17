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
    assert len(text_requests) == 3  # docfunnel route: parsed text, no file
    assert "<document>" in text_requests[0].messages[1].content
    # Budget: $3 spent after the docfunnel route, so one native call runs, two are skipped.
    assert len(file_requests) == 1
    assert file_requests[0].attachments[0].media_type == "application/pdf"
    assert file_requests[0].messages[1].content == ATTACHED_DOCUMENT_PROMPT
    assert report.meta.skipped_calls == 2
    assert report.meta.spent_usd == {"scripted": 4.0}

    by_route = {g.route: g.metrics for g in report.groups if g.slice == "all"}
    assert by_route["docfunnel"].documents == 3
    assert by_route["native"].documents == 1
    assert by_route["docfunnel"].field_accuracy > 0

    json_path, md_path = write_e2e_report(report, tmp_path)
    assert load_e2e_report(json_path).meta == report.meta
    markdown = md_path.read_text()
    assert "| `cheap-model` | docfunnel | 3 |" in markdown
    assert "### Native against docfunnel" in markdown
    assert "skipped calls (budget reached): 2" in markdown
