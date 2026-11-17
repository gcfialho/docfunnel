"""Score parsed documents against the PDF ground truth: routing, CER/WER, field recall."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from docfunnel.datasets.pdfs import DocTruth
from docfunnel.evals.parse.models import (
    FieldRecall,
    PageRecord,
    RoutingMetrics,
    TextQuality,
)
from docfunnel.evals.stats import safe_div
from docfunnel.evals.text import edit_counts, quote_found
from docfunnel.parse.model import ParsedDocument


def page_kind(scanned: bool, noise: str | None) -> str:
    return f"scanned_{noise}" if scanned else "digital"


@dataclass
class _Accumulator:
    pages: int = 0
    char_edits: int = 0
    chars: int = 0
    word_edits: int = 0
    words: int = 0

    def add(self, counts: tuple[int, int, int, int]) -> None:
        self.pages += 1
        self.char_edits += counts[0]
        self.chars += counts[1]
        self.word_edits += counts[2]
        self.words += counts[3]

    def result(self) -> TextQuality:
        return TextQuality(
            pages=self.pages,
            chars=self.chars,
            words=self.words,
            cer=safe_div(self.char_edits, self.chars),
            wer=safe_div(self.word_edits, self.words),
        )


def score_routing(truths: Sequence[DocTruth], docs: Sequence[ParsedDocument]) -> RoutingMetrics:
    tp = fp = fn = tn = 0
    by_route: dict[str, int] = {}
    for truth, doc in zip(truths, docs, strict=True):
        for label, page in zip(truth.pages, doc.pages, strict=True):
            by_route[page.route] = by_route.get(page.route, 0) + 1
            if page.needs_ocr and label.scanned:
                tp += 1
            elif page.needs_ocr:
                fp += 1
            elif label.scanned:
                fn += 1
            else:
                tn += 1
    total = tp + fp + fn + tn
    return RoutingMetrics(
        pages=total,
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
        precision=safe_div(tp, tp + fp),
        recall=safe_div(tp, tp + fn),
        accuracy=(tp + tn) / total if total else 0.0,
        by_route=dict(sorted(by_route.items())),
    )


def score_engine(
    truths: Sequence[DocTruth], docs: Sequence[ParsedDocument]
) -> tuple[dict[str, TextQuality], dict[str, FieldRecall], list[PageRecord]]:
    quality: dict[str, _Accumulator] = {}
    recall: dict[str, list[int]] = {}
    records = []
    for truth, doc in zip(truths, docs, strict=True):
        if len(doc.pages) != len(truth.pages):
            raise ValueError(
                f"{truth.id}: parsed {len(doc.pages)} pages, expected {len(truth.pages)}"
            )
        for label, page in zip(truth.pages, doc.pages, strict=True):
            kind = page_kind(label.scanned, label.noise)
            counts = edit_counts(label.text, page.text)
            for key in (kind, "scanned") if label.scanned else (kind,):
                quality.setdefault(key, _Accumulator()).add(counts)
            records.append(
                PageRecord(
                    doc_id=truth.id,
                    page=page.number,
                    kind=kind,
                    background=label.background,
                    stray_text=bool(label.stray_text),
                    route=page.route,
                    source=page.source,
                    cer=safe_div(counts[0], counts[1]),
                    wer=safe_div(counts[2], counts[3]),
                    total_ms=page.timings_ms.get("total", 0.0),
                )
            )
        for fld in truth.fields:
            gold = truth.pages[fld.page - 1]
            hit = int(quote_found(fld.quote, doc.pages[fld.page - 1].text))
            for key in (page_kind(gold.scanned, gold.noise), "all"):
                bucket = recall.setdefault(key, [0, 0])
                bucket[0] += hit
                bucket[1] += 1
    for key in ("digital", "scanned"):
        quality.setdefault(key, _Accumulator())
    recall.setdefault("all", [0, 0])
    return (
        {key: acc.result() for key, acc in sorted(quality.items())},
        {
            key: FieldRecall(fields=total, found=found, recall=safe_div(found, total))
            for key, (found, total) in sorted(recall.items())
        },
        records,
    )
