"""The index and chart of committed end-to-end runs: content, and no drift from the reports."""

from __future__ import annotations

import shutil
from pathlib import Path
from xml.etree import ElementTree

from docfunnel.evals.e2e.summary import chart_points, load_runs, model_name, write_summary

RUNS = Path(__file__).resolve().parents[2] / "reports" / "e2e"
CHART = RUNS.parents[1] / "docs" / "img" / "e2e-accuracy-vs-cost.svg"


def test_committed_index_and_chart_match_the_reports(tmp_path: Path) -> None:
    copy = tmp_path / "e2e"
    shutil.copytree(RUNS, copy)
    index, chart = write_summary(copy, tmp_path / "chart.svg")
    message = "run `docfunnel e2e-summary reports/e2e` and commit the result"
    assert index.read_text() == (RUNS / "README.md").read_text(), message
    assert chart.read_text() == CHART.read_text(), message


def test_index_lists_every_run_and_result() -> None:
    runs = load_runs(RUNS)
    readme = (RUNS / "README.md").read_text()
    for run in runs:
        assert f"[{run.name}]({run.name}/report.md)" in readme
    assert "| 07-gpt-6-luna-hybrid-ocr | GPT-6 Luna | hybrid-ocr | 39 | 100.0% |" in readme


def test_chart_keeps_comparable_results_once() -> None:
    points = chart_points(load_runs(RUNS))
    keys = [(p.model, p.route) for p in points]
    assert len(keys) == len(set(keys))  # a model and route measured twice appears once
    assert all("+" not in p.model for p in points)  # no effort or thinking variants
    assert {p.run for p in points} <= {
        "01-small-models",
        "06-gpt-6-luna",
        "07-gpt-6-luna-hybrid-ocr",
    }
    best = max(points, key=lambda p: p.exact_match)
    assert (best.model, best.route, best.exact_match) == ("gpt-6-luna", "hybrid-ocr", 1.0)

    svg = ElementTree.fromstring(CHART.read_text())
    circles = svg.findall(".//{http://www.w3.org/2000/svg}circle[@class]")
    assert sum("dot" in c.get("class", "") for c in circles) == len(points)
    labels = "".join(t.text or "" for t in svg.iter("{http://www.w3.org/2000/svg}text"))
    assert "GPT-6 Luna, hybrid-ocr: 100.0%" in labels


def test_model_names() -> None:
    assert model_name("gpt-6-luna") == "GPT-6 Luna"
    assert model_name("claude-haiku-5-5+effort=medium") == "Claude Haiku 5.5 (effort=medium)"
    assert model_name("some-new-model") == "some-new-model"


def test_paired_comparisons_and_intervals() -> None:
    from docfunnel.evals.e2e.summary import paired_comparisons
    from docfunnel.evals.stats import mcnemar_exact_p, wilson_interval

    assert mcnemar_exact_p(6, 0) == 2 / 64  # 6 to 0: the smallest split below 0.05
    assert mcnemar_exact_p(0, 0) == 1.0
    low, high = wilson_interval(39, 39)
    assert high == 1.0
    assert 0.90 < low < 0.92  # 39 of 39 still allows ~91%

    pairs = paired_comparisons(load_runs(RUNS))
    keys = [(a.model, a.route, b.route) for a, b, *_ in pairs]
    assert len(keys) == len(set(keys))
    gpt = {(a.route, b.route): (only_a, only_b, p) for a, b, _, only_a, only_b, p in pairs}
    assert gpt[("hybrid-ocr", "native")] == (6, 0, 2 / 64)
    readme = (RUNS / "README.md").read_text()
    assert "| GPT-6 Luna | hybrid-ocr | native | 39 | 6 | 0 | 0.031 |" in readme
