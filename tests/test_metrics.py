from decimal import Decimal

import pytest

from docfunnel.evals.metrics import (
    Outcome,
    compare_field,
    f1,
    match_line_items,
    percentile,
    score_header_fields,
)
from docfunnel.schema import LineItem, ReceiptData


@pytest.mark.parametrize(
    ("field", "predicted", "expected", "outcome"),
    [
        ("total", "1.234,50", Decimal("1234.50"), Outcome.CORRECT),
        ("total", 1234.51, Decimal("1234.50"), Outcome.CORRECT),  # cent tolerance
        ("total", 1234.60, Decimal("1234.50"), Outcome.INCORRECT),
        ("date", "15/03/2024", "2024-03-15", Outcome.CORRECT),
        ("date", "2024-03-16", "2024-03-15", Outcome.INCORRECT),
        ("vendor_name", "PADARIA PÃO DOURADO", "Padaria Pão Dourado", Outcome.CORRECT),
        ("vendor_tax_id", "12345678000190", "12.345.678/0001-90", Outcome.CORRECT),
        ("currency", "€", "EUR", Outcome.CORRECT),
        ("payment_method", "card", "cash", Outcome.INCORRECT),
        ("tax", None, None, Outcome.TRUE_NEGATIVE),
        ("tax", 1.0, None, Outcome.HALLUCINATED),
        ("tax", None, 1.0, Outcome.MISSED),
        ("total", "not a number", Decimal("1.00"), Outcome.INCORRECT),
    ],
)
def test_compare_field(field: str, predicted: object, expected: object, outcome: Outcome) -> None:
    assert compare_field(field, predicted, expected) is outcome


def test_score_header_fields_for_failed_extraction() -> None:
    gold = ReceiptData(vendor_name="Shop", total=Decimal("5"))
    outcomes = score_header_fields(None, gold)
    assert outcomes["vendor_name"] is Outcome.MISSED
    assert outcomes["tax"] is Outcome.TRUE_NEGATIVE


def item(desc: str, total: str, qty: int | None = None) -> LineItem:
    return LineItem(
        description=desc, total=Decimal(total), quantity=None if qty is None else Decimal(qty)
    )


def test_line_item_matching_is_one_to_one_and_typo_tolerant() -> None:
    gold = [item("Iced Tea", "8.25", 3), item("Hammer 16oz", "18.99"), item("Latte", "4.50")]
    pred = [
        item("lced Tea", "8.25", 3),
        item("Hammer 16oz", "18.99", 1),
        item("Hammer 16oz", "18.99"),
        item("Latte", "4.60"),
    ]
    assert match_line_items(pred, gold) == (2, 2, 1)


def test_line_item_quantity_must_match() -> None:
    assert match_line_items([item("Tea", "8.25", 2)], [item("Tea", "8.25", 3)]) == (0, 1, 1)


def test_percentile_matches_numpy_linear_convention() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert percentile(values, 50) == 3.0
    assert percentile(values, 95) == pytest.approx(80.8)
    assert percentile([], 50) is None
    assert percentile([7.0], 95) == 7.0


def test_f1() -> None:
    assert f1(1.0, 0.5) == pytest.approx(2 / 3)
    assert f1(None, 1.0) is None
    assert f1(0.0, 0.0) is None
