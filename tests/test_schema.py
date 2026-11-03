import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from docfunnel.schema import PaymentMethod, ReceiptExtraction


def test_lenient_coercion_of_llm_style_values() -> None:
    doc = ReceiptExtraction.model_validate(
        {
            "vendor_name": "  ",
            "date": "15/03/2024",
            "currency": "R$",
            "total": "1.234,50",
            "payment_method": "Bank Transfer",
            "line_items": [{"description": "x", "quantity": "2", "total": "3,00"}],
        }
    )
    assert doc.vendor_name is None
    assert doc.date == date(2024, 3, 15)
    assert doc.currency == "BRL"
    assert doc.total == Decimal("1234.50")
    assert doc.payment_method is PaymentMethod.BANK_TRANSFER
    assert doc.line_items[0].quantity == Decimal("2")


def test_json_serialization_uses_numbers_not_strings() -> None:
    doc = ReceiptExtraction.model_validate({"total": "12.50", "date": "2024-01-02"})
    data = json.loads(doc.model_dump_json())
    assert data["total"] == 12.5
    assert data["date"] == "2024-01-02"


def test_confidence_is_clamped_and_unknown_keys_dropped() -> None:
    doc = ReceiptExtraction.model_validate(
        {"field_confidence": {"total": 1.7, "date": -1, "made_up": 0.5, "tax": "high"}}
    )
    assert doc.field_confidence == {"total": 1.0, "date": 0.0}


@pytest.mark.parametrize(
    "payload",
    [
        {"total": "see line items"},
        {"line_items": "n/a"},
        {"line_items": [{"description": "no total"}]},
        {"unexpected_field": 1},
        {"payment_method": "cheque"},
        {"date": "someday"},
    ],
)
def test_schema_violations_are_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ReceiptExtraction.model_validate(payload)


def test_to_data_drops_confidence() -> None:
    doc = ReceiptExtraction.model_validate({"total": 1, "field_confidence": {"total": 0.9}})
    assert "field_confidence" not in doc.to_data().model_dump()
