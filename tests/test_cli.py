import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from docfunnel.cli import app

from helpers import DATASET, US_RECEIPT

runner = CliRunner()


@pytest.fixture(autouse=True)
def offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DOCFUNNEL_PROVIDER", "DOCFUNNEL_MODEL", "DOCFUNNEL_FALLBACK"):
        monkeypatch.delenv(name, raising=False)


def test_extract_file(tmp_path: Path) -> None:
    source = tmp_path / "receipt.txt"
    source.write_text(US_RECEIPT)
    result = runner.invoke(app, ["extract", str(source), "--model", "fake-pro"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["document"]["total"] == 29.42


def test_extract_stdin_and_fail_on_review() -> None:
    misprinted = US_RECEIPT.replace("$29.42", "$99.42")
    result = runner.invoke(
        app,
        ["extract", "-", "-m", "fake-pro", "--fail-on-review", "--no-include-calls"],
        input=misprinted,
    )
    assert result.exit_code == 3
    assert "calls" not in json.loads(result.output)


def test_extract_reports_configuration_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source = tmp_path / "r.txt"
    source.write_text(US_RECEIPT)
    result = runner.invoke(app, ["extract", str(source), "--provider", "openai"])
    assert result.exit_code == 2


@pytest.mark.integration
def test_eval_then_compare(tmp_path: Path) -> None:
    base_dir, cand_dir = tmp_path / "base", tmp_path / "cand"
    common = ["eval", "--dataset", str(DATASET), "--limit", "25"]
    assert (
        runner.invoke(app, [*common, "--out", str(base_dir), "-f", "fake:fake-pro"]).exit_code == 0
    )
    assert runner.invoke(app, [*common, "--out", str(cand_dir)]).exit_code == 0
    assert (base_dir / "report.md").exists()

    same = runner.invoke(
        app, ["compare", str(base_dir / "report.json"), str(base_dir / "report.json")]
    )
    assert same.exit_code == 0
    assert "PASS" in same.output

    out = tmp_path / "comparison.md"
    worse = runner.invoke(
        app,
        [
            "compare",
            str(base_dir / "report.json"),
            str(cand_dir / "report.json"),
            "--out",
            str(out),
        ],
    )
    assert worse.exit_code == 1, worse.output
    assert "REGRESSION" in out.read_text()


def test_generate_dataset(tmp_path: Path) -> None:
    out = tmp_path / "d.jsonl"
    result = runner.invoke(app, ["generate-dataset", "--out", str(out), "--n", "5"])
    assert result.exit_code == 0
    assert len(out.read_text().splitlines()) == 5
