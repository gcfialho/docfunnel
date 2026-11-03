"""Business rules and the human-in-the-loop review decision.

Schema validation (pydantic) answers "is this well-formed?". The rules here answer
"is this plausible?" - arithmetic consistency, required fields, sane dates. Rule
violations never trigger an LLM retry (the document itself may be inconsistent);
they route the result to a human instead.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from docextract.normalize import ISO_CURRENCIES
from docextract.schema import (
    CONFIDENCE_FIELDS,
    ReceiptExtraction,
    Severity,
    ValidationIssue,
)

REQUIRED_FIELDS: tuple[str, ...] = ("vendor_name", "date", "total", "currency")


@dataclass(frozen=True)
class ReviewPolicy:
    """Knobs for routing results to human review."""

    min_confidence: float = 0.7
    abs_tolerance: Decimal = Decimal("0.02")
    rel_tolerance: Decimal = Decimal("0.005")
    min_year: int = 2000
    max_days_in_future: int = 1


def _close(a: Decimal, b: Decimal, policy: ReviewPolicy) -> bool:
    tolerance = max(policy.abs_tolerance, abs(b) * policy.rel_tolerance)
    return abs(a - b) <= tolerance


def check_business_rules(
    doc: ReceiptExtraction,
    policy: ReviewPolicy | None = None,
    *,
    today: dt.date | None = None,
) -> list[ValidationIssue]:
    """Return every business-rule issue found on a schema-valid extraction."""
    policy = policy or ReviewPolicy()
    today = today or dt.date.today()
    issues: list[ValidationIssue] = []

    def add(code: str, message: str, severity: Severity, *fields: str) -> None:
        issues.append(
            ValidationIssue(code=code, message=message, severity=severity, fields=list(fields))
        )

    for name in REQUIRED_FIELDS:
        if getattr(doc, name) is None:
            add("missing_required_field", f"{name} is missing", Severity.ERROR, name)

    if doc.currency is not None and doc.currency not in ISO_CURRENCIES:
        add(
            "unknown_currency",
            f"currency {doc.currency!r} is not a supported ISO 4217 code",
            Severity.WARNING,
            "currency",
        )

    for label, value in (("subtotal", doc.subtotal), ("tax", doc.tax), ("total", doc.total)):
        if value is not None and value < 0:
            add("negative_amount", f"{label} is negative ({value})", Severity.ERROR, label)

    if doc.date is not None:
        if doc.date.year < policy.min_year:
            add(
                "implausible_date",
                f"date {doc.date} is before {policy.min_year}",
                Severity.ERROR,
                "date",
            )
        elif (doc.date - today).days > policy.max_days_in_future:
            add("future_date", f"date {doc.date} is in the future", Severity.ERROR, "date")

    for index, item in enumerate(doc.line_items):
        if item.quantity is not None and item.unit_price is not None:
            expected = item.quantity * item.unit_price
            if not _close(item.total, expected, policy):
                add(
                    "line_item_arithmetic",
                    f"line {index + 1}: {item.quantity} x {item.unit_price} != {item.total}",
                    Severity.WARNING,
                    "line_items",
                )

    if doc.line_items and doc.subtotal is not None:
        items_sum = sum((item.total for item in doc.line_items), Decimal("0"))
        if not _close(items_sum, doc.subtotal, policy):
            add(
                "line_items_sum_mismatch",
                f"line items sum to {items_sum} but subtotal is {doc.subtotal}",
                Severity.ERROR,
                "line_items",
                "subtotal",
            )

    if doc.total is not None:
        if doc.subtotal is not None:
            expected_total = doc.subtotal + (doc.tax or Decimal("0"))
            if not _close(doc.total, expected_total, policy):
                add(
                    "total_mismatch",
                    f"subtotal {doc.subtotal} + tax {doc.tax or 0} != total {doc.total}",
                    Severity.ERROR,
                    "subtotal",
                    "tax",
                    "total",
                )
        elif doc.line_items:
            # Without a printed subtotal, accept both tax-exclusive item prices
            # (items + tax = total) and tax-inclusive ones (items = total, tax shown
            # for information - common on EU retail receipts).
            items_sum = sum((item.total for item in doc.line_items), Decimal("0"))
            candidates = {items_sum, items_sum + (doc.tax or Decimal("0"))}
            if not any(_close(doc.total, expected, policy) for expected in candidates):
                add(
                    "line_items_total_mismatch",
                    f"line items sum to {items_sum} (tax {doc.tax or 0}) but total is {doc.total}",
                    Severity.ERROR,
                    "line_items",
                    "total",
                )

    return issues


def review_decision(
    doc: ReceiptExtraction | None,
    issues: list[ValidationIssue],
    policy: ReviewPolicy | None = None,
) -> tuple[bool, list[str]]:
    """Decide whether a human must look at this result, and why.

    Reasons are short, stable strings so they can be aggregated in dashboards.
    """
    policy = policy or ReviewPolicy()
    if doc is None:
        return True, ["extraction_failed"]

    reasons: list[str] = [
        f"{issue.code}:{','.join(issue.fields)}" if issue.fields else issue.code
        for issue in issues
        if issue.severity is Severity.ERROR
    ]
    for name in CONFIDENCE_FIELDS:
        score = doc.field_confidence.get(name)
        is_present = (
            bool(doc.line_items) if name == "line_items" else (getattr(doc, name) is not None)
        )
        if is_present and score is not None and score < policy.min_confidence:
            reasons.append(f"low_confidence:{name}")
    return bool(reasons), reasons
