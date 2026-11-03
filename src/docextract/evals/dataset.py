"""Labelled dataset loading (JSONL: one document per line)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from docextract.schema import ReceiptData

DEFAULT_DATASET = Path("data/synthetic/receipts.jsonl")


@dataclass(frozen=True)
class LabeledDocument:
    id: str
    text: str
    label: ReceiptData
    expected_review: bool = False
    tags: dict[str, str] = field(default_factory=dict)


def load_dataset(path: Path, *, limit: int | None = None) -> list[LabeledDocument]:
    documents: list[LabeledDocument] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                documents.append(
                    LabeledDocument(
                        id=raw["id"],
                        text=raw["text"],
                        label=ReceiptData.model_validate(raw["label"]),
                        expected_review=bool(raw.get("expected_review", False)),
                        tags={k: str(raw[k]) for k in ("layout", "locale", "variant") if k in raw},
                    )
                )
            except (KeyError, ValueError) as exc:
                raise ValueError(f"{path}:{line_number}: invalid record: {exc}") from exc
            if limit is not None and len(documents) >= limit:
                break
    return documents


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
