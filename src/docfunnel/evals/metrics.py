"""Scoring for non-deterministic extraction output.

Each header field of each document gets exactly one outcome:

* ``correct``        - prediction equals ground truth after normalization;
* ``true_negative``  - both are null (the field is absent and the model said so);
* ``incorrect``      - both present but different;
* ``missed``         - ground truth present, prediction null;
* ``hallucinated``   - ground truth null, prediction present (an invented value).

Field accuracy counts ``correct`` and ``true_negative`` as right. Hallucination rate
is ``hallucinated / (hallucinated + true_negative)``: of the fields that are *not* on
the document, how often did the model fill them anyway?
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

from docfunnel.normalize import (
    amounts_close,
    normalize_currency,
    normalize_identifier,
    normalize_text,
    parse_amount,
    parse_date,
)
from docfunnel.schema import HEADER_FIELDS, LineItem, ReceiptData


class Outcome(StrEnum):
    CORRECT = "correct"
    TRUE_NEGATIVE = "true_negative"
    INCORRECT = "incorrect"
    MISSED = "missed"
    HALLUCINATED = "hallucinated"

    @property
    def is_right(self) -> bool:
        return self in (Outcome.CORRECT, Outcome.TRUE_NEGATIVE)


_MONEY_FIELDS = {"subtotal", "tax", "total"}
_ID_FIELDS = {"vendor_tax_id", "document_number"}


def normalize_field(name: str, value: Any) -> Any:
    """Normalize a header field value to its canonical comparable form (or None)."""
    if value is None:
        return None
    try:
        if name in _MONEY_FIELDS:
            return parse_amount(value)
        if name == "date":
            parsed = parse_date(value)
            return parsed.isoformat() if parsed else None
        if name == "currency":
            return normalize_currency(value)
        if name in _ID_FIELDS:
            return normalize_identifier(value)
        if name == "payment_method":
            return normalize_text(getattr(value, "value", value))
        return normalize_text(value)
    except ValueError:
        # Unparseable prediction: keep the raw text so it is scored as incorrect.
        return normalize_text(value)


def compare_field(name: str, predicted: Any, expected: Any) -> Outcome:
    pred, gold = normalize_field(name, predicted), normalize_field(name, expected)
    if gold is None:
        return Outcome.TRUE_NEGATIVE if pred is None else Outcome.HALLUCINATED
    if pred is None:
        return Outcome.MISSED
    if isinstance(gold, Decimal) and isinstance(pred, Decimal):
        return Outcome.CORRECT if amounts_close(pred, gold) else Outcome.INCORRECT
    return Outcome.CORRECT if pred == gold else Outcome.INCORRECT


def score_header_fields(predicted: ReceiptData | None, expected: ReceiptData) -> dict[str, Outcome]:
    return {
        name: compare_field(
            name, getattr(predicted, name) if predicted else None, getattr(expected, name)
        )
        for name in HEADER_FIELDS
    }


def _items_match(pred: LineItem, gold: LineItem, min_similarity: float) -> bool:
    if not amounts_close(pred.total, gold.total):
        return False
    if (pred.quantity or Decimal(1)) != (gold.quantity or Decimal(1)):
        return False
    ratio = SequenceMatcher(
        None, normalize_text(pred.description) or "", normalize_text(gold.description) or ""
    ).ratio()
    return ratio >= min_similarity


def match_line_items(
    predicted: Sequence[LineItem], expected: Sequence[LineItem], *, min_similarity: float = 0.8
) -> tuple[int, int, int]:
    """Greedy one-to-one matching; returns (true positives, false positives, false negatives).

    A predicted item matches a gold item when totals agree (to the cent), quantities
    agree (missing = 1) and descriptions are similar (tolerates OCR typos).
    """
    unmatched = list(predicted)
    tp = 0
    for gold in expected:
        for i, pred in enumerate(unmatched):
            if _items_match(pred, gold, min_similarity):
                tp += 1
                del unmatched[i]
                break
    return tp, len(unmatched), len(expected) - tp


def safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return 2 * precision * recall / (precision + recall)


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Linear-interpolated percentile (same convention as numpy's default)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


# ---- text metrics for the parse stage ------------------------------------------------


def normalize_whitespace(text: str) -> str:
    """Collapse every run of whitespace (including line breaks) to one space.

    CER and WER are measured on this form: the parse stage is judged on the
    characters it recovers and their order, not on how it splits lines or columns.
    """
    return " ".join(text.split())


def edit_counts(reference: str, hypothesis: str) -> tuple[int, int, int, int]:
    """``(char_edits, ref_chars, word_edits, ref_words)`` after whitespace normalization."""
    from rapidfuzz.distance import Levenshtein

    ref, hyp = normalize_whitespace(reference), normalize_whitespace(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    return (
        Levenshtein.distance(ref, hyp),
        len(ref),
        Levenshtein.distance(ref_words, hyp_words),
        len(ref_words),
    )


def char_error_rate(reference: str, hypothesis: str) -> float:
    edits, chars, _, _ = edit_counts(reference, hypothesis)
    return edits / chars if chars else float(bool(normalize_whitespace(hypothesis)))


def word_error_rate(reference: str, hypothesis: str) -> float:
    _, _, edits, words = edit_counts(reference, hypothesis)
    return edits / words if words else float(bool(normalize_whitespace(hypothesis)))


def quote_found(quote: str, text: str) -> bool:
    """Does the printed value appear in the parsed text? Whitespace is ignored."""
    return "".join(quote.split()) in "".join(text.split())
