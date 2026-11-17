"""The end-to-end set: invoices as PDFs, small (the generated set) and large (with annexes).

* **small**: every invoice of the synthetic PDF set as it is: 1 to 4 pages, 17 to 170
  line items, digital, scanned or mixed.
* **large**: an invoice followed by contracts from the same set, as annexes, until the
  PDF has 8 to 13 pages. The label stays the invoice's; the contracts add pages to read
  and distractors (parties, fees, dates). The text stays under the extractor's
  character limit, so both routes see the whole document.

Requires the ``synthetic`` extra to build (pypdfium2 merges the PDFs).
"""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docfunnel.datasets.pdfs import DocTruth, load_manifest
from docfunnel.extract.extractor import MAX_DOCUMENT_CHARS
from docfunnel.extract.schema import ReceiptData

MANIFEST = "e2e.jsonl"
_LABEL_FIELDS = frozenset(ReceiptData.model_fields)


@dataclass(frozen=True)
class E2EDoc:
    id: str
    file: str
    size: str  # "small" | "large"
    pages: int
    scanned_pages: int
    variant: str
    label: ReceiptData

    @property
    def tags(self) -> dict[str, str]:
        return {
            "size": self.size,
            "scan": "has_scanned_pages" if self.scanned_pages else "digital",
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file": self.file,
            "size": self.size,
            "pages": self.pages,
            "scanned_pages": self.scanned_pages,
            "variant": self.variant,
            "label": self.label.model_dump(mode="json"),
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> E2EDoc:
        return cls(
            id=raw["id"],
            file=raw["file"],
            size=raw["size"],
            pages=raw["pages"],
            scanned_pages=raw["scanned_pages"],
            variant=raw["variant"],
            label=ReceiptData.model_validate(raw["label"]),
        )


def _label(truth: DocTruth) -> ReceiptData:
    # The generator also labels distractors such as the "Bill to" customer; keep the schema.
    return ReceiptData.model_validate({k: v for k, v in truth.label.items() if k in _LABEL_FIELDS})


def _chars(truth: DocTruth) -> int:
    return sum(len(page.text) for page in truth.pages)


def build_e2e_set(
    pdf_dir: Path, out_dir: Path, *, n_large: int = 10, seed: int = 5
) -> list[E2EDoc]:
    """Write the small and large PDFs and ``e2e.jsonl`` to ``out_dir``."""
    import pypdfium2 as pdfium

    truths = load_manifest(pdf_dir)
    invoices = [t for t in truths if t.doc_type == "invoice"]
    contracts = [t for t in truths if t.doc_type == "contract"]
    if not invoices or not contracts:
        raise ValueError(f"{pdf_dir} needs invoices and contracts; run docfunnel generate-pdfs")
    out_dir.mkdir(parents=True, exist_ok=True)
    docs: list[E2EDoc] = []
    for truth in invoices:
        shutil.copyfile(pdf_dir / truth.file, out_dir / truth.file)
        docs.append(
            E2EDoc(
                id=truth.id,
                file=truth.file,
                size="small",
                pages=len(truth.pages),
                scanned_pages=sum(p.scanned for p in truth.pages),
                variant=truth.variant,
                label=_label(truth),
            )
        )

    rng = random.Random(seed)
    short = [t for t in invoices if len(t.pages) <= 2] or invoices
    budget = int(MAX_DOCUMENT_CHARS * 0.9)  # leave room for page separators and OCR noise
    for index in range(n_large):
        invoice = short[index % len(short)]
        parts, chars = [invoice], _chars(invoice)
        for contract in rng.sample(contracts, len(contracts)):
            pages = sum(len(p.pages) for p in parts)
            if pages >= 8 or chars + _chars(contract) > budget:
                break
            parts.append(contract)
            chars += _chars(contract)
        merged = pdfium.PdfDocument.new()
        for part in parts:
            source = pdfium.PdfDocument(str(pdf_dir / part.file))
            merged.import_pages(source)
            source.close()
        doc_id = f"large-{index:02d}"
        merged.save(str(out_dir / f"{doc_id}.pdf"))
        merged.close()
        docs.append(
            E2EDoc(
                id=doc_id,
                file=f"{doc_id}.pdf",
                size="large",
                pages=sum(len(p.pages) for p in parts),
                scanned_pages=sum(pg.scanned for p in parts for pg in p.pages),
                variant="+".join(sorted({p.variant for p in parts})),
                label=_label(invoice),
            )
        )
    lines = [json.dumps(doc.to_json(), ensure_ascii=False) for doc in docs]
    (out_dir / MANIFEST).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return docs


def load_e2e_set(directory: Path) -> list[E2EDoc]:
    path = directory / MANIFEST
    if not path.is_file():
        raise ValueError(f"{path} not found; run 'docfunnel generate-e2e' first")
    return [
        E2EDoc.from_json(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
