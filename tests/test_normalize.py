from datetime import date
from decimal import Decimal

import pytest

from docfunnel.normalize import (
    amounts_close,
    normalize_currency,
    normalize_identifier,
    normalize_text,
    parse_amount,
    parse_date,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.50", "12.50"),
        ("$1,234.56", "1234.56"),
        ("1.234,56 €", "1234.56"),
        ("R$ 15.120,00", "15120.00"),
        ("12,5", "12.50"),
        ("1,234", "1234.00"),
        ("1.234.567", "1234567.00"),
        ("12. 50", "12.50"),
        ("(5.00)", "-5.00"),
        ("-3.10", "-3.10"),
        ("USD 99.999", "100.00"),
        (7, "7.00"),
        (19.999, "20.00"),
        (Decimal("2.345"), "2.35"),
    ],
)
def test_parse_amount(raw: object, expected: str) -> None:
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [None, "", "  ", "null", "N/A"])
def test_parse_amount_empty_is_none(raw: object) -> None:
    assert parse_amount(raw) is None


@pytest.mark.parametrize("raw", ["see line items", "abc", True, [1]])
def test_parse_amount_rejects_garbage(raw: object) -> None:
    with pytest.raises(ValueError, match="amount"):
        parse_amount(raw)


@pytest.mark.parametrize(
    ("raw", "dayfirst", "expected"),
    [
        ("2024-03-15", True, date(2024, 3, 15)),
        ("2024-03-15T14:22:00", True, date(2024, 3, 15)),
        ("2023-08-26 16:41", True, date(2023, 8, 26)),
        ("15.03.2024", True, date(2024, 3, 15)),
        ("03/04/2024", True, date(2024, 4, 3)),
        ("03/04/2024", False, date(2024, 3, 4)),
        ("13/04/2024", False, date(2024, 4, 13)),  # unambiguous despite the hint
        ("14 Dec 2024", True, date(2024, 12, 14)),
        ("Dec 14, 2024", True, date(2024, 12, 14)),
        ("March 5, 2024", True, date(2024, 3, 5)),
        ("05/03/24", True, date(2024, 3, 5)),
        (date(2024, 1, 2), True, date(2024, 1, 2)),
    ],
)
def test_parse_date(raw: object, dayfirst: bool, expected: date) -> None:
    assert parse_date(raw, dayfirst=dayfirst) == expected


@pytest.mark.parametrize("raw", ["yesterday", "31/02/2024", "2024-13-01x"])
def test_parse_date_rejects_garbage(raw: str) -> None:
    with pytest.raises(ValueError, match="date"):
        parse_date(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("R$", "BRL"), ("€", "EUR"), ("£", "GBP"), ("$", "USD"), ("usd", "USD"), ("", None)],
)
def test_normalize_currency(raw: str, expected: str | None) -> None:
    assert normalize_currency(raw) == expected


def test_normalize_currency_rejects_words() -> None:
    with pytest.raises(ValueError, match="currency"):
        normalize_currency("dollars")


def test_normalize_text_is_case_and_space_insensitive() -> None:
    assert normalize_text("  PADARIA   Pão Dourado. ") == normalize_text("padaria pão dourado")
    assert normalize_text("  ") is None


def test_normalize_identifier_ignores_punctuation() -> None:
    assert normalize_identifier("12.345.678/0001-90") == "12345678000190"
    assert normalize_identifier("GB 123 4567 89") == normalize_identifier("gb123456789")


def test_amounts_close() -> None:
    assert amounts_close(Decimal("10.00"), Decimal("10.01"))
    assert not amounts_close(Decimal("10.00"), Decimal("10.02"))
    assert amounts_close(None, None)
    assert not amounts_close(None, Decimal("1"))
