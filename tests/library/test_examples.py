"""The scripts in examples/ run offline and do what their docstrings say."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_invoice_inbox_accepts_and_queues(tmp_path: Path) -> None:
    out = tmp_path / "out"
    env = {"DOCFUNNEL_PROVIDER": "fake", "PATH": ""}
    script = ROOT / "examples" / "invoice_inbox.py"
    run = subprocess.run(
        [sys.executable, str(script), str(ROOT / "examples"), "--out", str(out)],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=300,
    )
    assert "5 documents: 3 accepted, 2 sent to review" in run.stdout
    with (out / "accepted.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert {r["file"] for r in rows} >= {"receipt_us.txt", "invoice_br.txt"}
    review = [json.loads(line) for line in (out / "review.jsonl").read_text().splitlines()]
    reasons = {r["file"]: r["reasons"] for r in review}
    assert any(r.startswith("total_mismatch") for r in reasons["receipt_misprinted.txt"])
