from datetime import date

from docextract.schema import ReceiptExtraction
from docextract.validation import ReviewPolicy, check_business_rules, review_decision

TODAY = date(2025, 6, 1)


def make(**overrides: object) -> ReceiptExtraction:
    base = {
        "vendor_name": "Shop",
        "date": "2025-01-10",
        "currency": "USD",
        "subtotal": 10.00,
        "tax": 0.80,
        "total": 10.80,
        "line_items": [
            {"description": "a", "quantity": 2, "unit_price": 2.5, "total": 5.0},
            {"description": "b", "quantity": 1, "unit_price": 5.0, "total": 5.0},
        ],
        "field_confidence": {"vendor_name": 0.9, "total": 0.95},
    }
    return ReceiptExtraction.model_validate(base | overrides)


def codes(doc: ReceiptExtraction) -> set[str]:
    return {issue.code for issue in check_business_rules(doc, today=TODAY)}


def test_consistent_document_has_no_issues() -> None:
    doc = make()
    assert codes(doc) == set()
    assert review_decision(doc, []) == (False, [])


def test_total_mismatch() -> None:
    assert "total_mismatch" in codes(make(total=12.00))


def test_rounding_within_tolerance_is_accepted() -> None:
    assert codes(make(total=10.81)) == set()


def test_line_items_must_sum_to_subtotal() -> None:
    assert "line_items_sum_mismatch" in codes(make(subtotal=11.00, total=11.80))


def test_line_items_checked_against_total_when_no_subtotal() -> None:
    doc = make(subtotal=None, tax=None, total=9.00)
    assert "line_items_total_mismatch" in codes(doc)


def test_tax_inclusive_and_exclusive_items_without_subtotal() -> None:
    assert codes(make(subtotal=None, tax=0.80, total=10.80)) == set()  # items + tax
    assert codes(make(subtotal=None, tax=1.60, total=10.00)) == set()  # VAT included
    assert "line_items_total_mismatch" in codes(make(subtotal=None, tax=0.80, total=11.50))


def test_line_item_arithmetic_is_a_warning() -> None:
    doc = make(
        line_items=[
            {"description": "a", "quantity": 3, "unit_price": 2.5, "total": 5.0},
            {"description": "b", "total": 5.0},
        ]
    )
    issues = check_business_rules(doc, today=TODAY)
    assert [(i.code, i.severity.value) for i in issues] == [("line_item_arithmetic", "warning")]
    assert review_decision(doc, issues) == (False, [])


def test_missing_required_fields() -> None:
    issues = check_business_rules(make(vendor_name=None, currency=None), today=TODAY)
    missing = {tuple(i.fields) for i in issues if i.code == "missing_required_field"}
    assert missing == {("vendor_name",), ("currency",)}


def test_dates_must_be_plausible() -> None:
    assert "future_date" in codes(make(date="2030-01-01"))
    assert "implausible_date" in codes(make(date="1990-01-01"))


def test_negative_amounts_and_unknown_currency() -> None:
    found = codes(make(tax=-0.80, total=9.20, currency="XYZ"))
    assert {"negative_amount", "unknown_currency"} <= found


def test_low_confidence_triggers_review_only_for_present_fields() -> None:
    doc = make(
        document_number=None,
        field_confidence={"total": 0.4, "document_number": 0.1, "vendor_name": 0.9},
    )
    needs_review, reasons = review_decision(doc, [], ReviewPolicy(min_confidence=0.7))
    assert needs_review
    assert reasons == ["low_confidence:total"]


def test_error_issues_become_review_reasons() -> None:
    doc = make(total=12.00)
    needs_review, reasons = review_decision(doc, check_business_rules(doc, today=TODAY))
    assert needs_review
    assert reasons == ["total_mismatch:subtotal,tax,total"]


def test_failed_extraction_always_needs_review() -> None:
    assert review_decision(None, []) == (True, ["extraction_failed"])
