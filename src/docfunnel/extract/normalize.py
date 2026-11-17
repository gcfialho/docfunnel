"""Deterministic normalization helpers shared by schema validation and evaluation.

LLMs (and OCR) emit the same value in many surface forms: ``"$1,234.50"``,
``"1.234,50 EUR"``, ``"15/03/2024"``, ``"March 15, 2024"``. Everything downstream
(business rules, metrics) compares *normalized* values, so these functions are the
single source of truth for what "the same value" means.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")

# Ordered longest-first so "R$" wins over "$".
CURRENCY_SYMBOLS: dict[str, str] = {
    "R$": "BRL",
    "US$": "USD",
    "€": "EUR",
    "£": "GBP",
    "$": "USD",
}

ISO_CURRENCIES = frozenset(
    {"USD", "EUR", "GBP", "BRL", "CAD", "AUD", "CHF", "JPY", "MXN", "ARS", "CLP", "COP", "INR"}
)

_AMOUNT_JUNK = re.compile(r"[^\d,.\-()]")
_WS = re.compile(r"\s+")

_DATE_FORMATS_YEAR_FIRST = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d")
_DATE_FORMATS_TEXTUAL = (
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%d-%b-%Y",
    "%d %b, %Y",
)
_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})$")


def parse_amount(value: object) -> Decimal | None:
    """Parse a monetary amount into a ``Decimal`` rounded to cents.

    Handles currency symbols/codes, US (``1,234.56``) and European (``1.234,56``)
    separators, stray whitespace from OCR (``12. 50``) and accounting negatives
    (``(5.00)``). Returns ``None`` for empty input and raises ``ValueError`` for
    input that is present but not a number.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("booleans are not amounts")
    if isinstance(value, Decimal):
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
    if isinstance(value, int | float):
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    if not isinstance(value, str):
        raise ValueError(f"unsupported amount type: {type(value).__name__}")

    raw = value.strip()
    if not raw or raw.lower() in {"null", "none", "n/a", "-"}:
        return None

    negative = raw.startswith("-") or raw.endswith("-") or (raw.startswith("(") and ")" in raw)
    cleaned = _AMOUNT_JUNK.sub("", raw.replace(" ", "")).strip("-()")
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        raise ValueError(f"not an amount: {value!r}")

    last_comma, last_dot = cleaned.rfind(","), cleaned.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        # Whichever separator comes last is the decimal separator.
        if last_comma > last_dot:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif last_comma >= 0:
        # "12,50" -> decimal comma; "1,234" / "1,234,567" -> thousands separators.
        head, _, tail = cleaned.rpartition(",")
        cleaned = cleaned.replace(",", "") if len(tail) == 3 else head.replace(",", "") + "." + tail
    elif cleaned.count(".") > 1:
        # "1.234.567" -> thousands separators; "1.234.56" -> last dot is the decimal point.
        head, _, tail = cleaned.rpartition(".")
        cleaned = cleaned.replace(".", "") if len(tail) == 3 else head.replace(".", "") + "." + tail

    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    if negative:
        amount = -amount
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_date(value: object, *, dayfirst: bool = True) -> date | None:
    """Parse common receipt date formats into a ``date``.

    ISO and textual month formats are unambiguous. For purely numeric ``a/b/yyyy``
    dates the ``dayfirst`` hint decides, unless one component is > 12.
    Returns ``None`` for empty input and raises ``ValueError`` otherwise.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"unsupported date type: {type(value).__name__}")

    raw = _WS.sub(" ", value.strip())
    if not raw or raw.lower() in {"null", "none", "n/a"}:
        return None
    # Drop a trailing time component ("2024-03-15 14:22" / "2024-03-15T14:22:00").
    raw = re.split(r"[T ](?=\d{1,2}:\d{2})", raw, maxsplit=1)[0].strip()

    for fmt in _DATE_FORMATS_YEAR_FIRST + _DATE_FORMATS_TEXTUAL:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    match = _NUMERIC_DATE.match(raw)
    if match:
        a, b, year_text = int(match[1]), int(match[2]), match[3]
        year = int(year_text) + (2000 if len(year_text) == 2 else 0)
        if a > 12 or (dayfirst and b <= 12):
            day, month = a, b
        else:
            month, day = a, b
        try:
            return date(year, month, day)
        except ValueError as exc:
            raise ValueError(f"invalid date: {value!r}") from exc

    raise ValueError(f"unrecognized date format: {value!r}")


def normalize_currency(value: object) -> str | None:
    """Map a currency symbol or code to an ISO 4217 code (``"R$"`` -> ``"BRL"``)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"unsupported currency type: {type(value).__name__}")
    raw = value.strip()
    if not raw:
        return None
    if raw in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[raw]
    code = raw.upper()
    if re.fullmatch(r"[A-Z]{3}", code):
        return code
    raise ValueError(f"not a currency code: {value!r}")


def normalize_text(value: object) -> str | None:
    """Canonical form for free-text comparison: NFKC, casefolded, collapsed whitespace,
    with surrounding punctuation removed. Returns ``None`` for empty strings."""
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = _WS.sub(" ", text).strip(" \t\n.,;:-_*#")
    return text or None


def normalize_identifier(value: object) -> str | None:
    """Canonical form for IDs (tax IDs, invoice numbers): uppercase alphanumerics only.

    ``"12.345.678/0001-90"`` and ``"12345678000190"`` compare equal.
    """
    if value is None:
        return None
    ident = re.sub(r"[^0-9A-Za-z]", "", unicodedata.normalize("NFKC", str(value))).upper()
    return ident or None


def amounts_close(a: Decimal | None, b: Decimal | None, *, abs_tol: str = "0.01") -> bool:
    """Equality for money with a small absolute tolerance (rounding noise)."""
    if a is None or b is None:
        return a is b
    return abs(a - b) <= Decimal(abs_tol)
