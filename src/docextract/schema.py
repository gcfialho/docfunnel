"""Pydantic contracts: what the LLM must return and what the service returns."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
)

from docextract.normalize import normalize_currency, parse_amount, parse_date


def _amount(value: Any) -> Decimal | None:
    return parse_amount(value)


def _iso_date(value: Any) -> dt.date | None:
    # The prompt asks for ISO 8601; anything else is accepted only if unambiguous
    # (dayfirst=True is the safe default for the non-US formats we ship).
    return parse_date(value, dayfirst=True)


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _to_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


Money = Annotated[
    Decimal,
    BeforeValidator(_amount),
    PlainSerializer(float, return_type=float, when_used="json"),
]
OptionalMoney = Annotated[
    Decimal | None,
    BeforeValidator(_amount),
    PlainSerializer(_to_float, return_type=float | None, when_used="json"),
]
OptionalQuantity = OptionalMoney
OptionalText = Annotated[str | None, BeforeValidator(_empty_to_none)]


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    PIX = "pix"
    OTHER = "other"


class LineItem(BaseModel):
    """A single purchased item as printed on the document."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    quantity: OptionalQuantity = None
    unit_price: OptionalMoney = None
    total: Money


# Fields the evaluator scores individually ("header" fields) - order matters for reports.
HEADER_FIELDS: tuple[str, ...] = (
    "vendor_name",
    "vendor_tax_id",
    "document_number",
    "date",
    "currency",
    "subtotal",
    "tax",
    "total",
    "payment_method",
)
CONFIDENCE_FIELDS: tuple[str, ...] = (*HEADER_FIELDS, "line_items")


class ReceiptData(BaseModel):
    """Ground-truth shaped document: the facts printed on a receipt or invoice.

    Every field is nullable on purpose: "not on the document" must be expressible,
    otherwise the model is pushed towards inventing values.
    """

    model_config = ConfigDict(extra="forbid")

    vendor_name: OptionalText = None
    vendor_tax_id: OptionalText = None
    document_number: OptionalText = None
    date: Annotated[dt.date | None, BeforeValidator(_iso_date)] = None
    currency: Annotated[str | None, BeforeValidator(normalize_currency)] = Field(
        default=None, description="ISO 4217 code, e.g. USD, EUR, GBP, BRL"
    )
    subtotal: OptionalMoney = None
    tax: OptionalMoney = None
    total: OptionalMoney = None
    payment_method: PaymentMethod | None = None
    line_items: list[LineItem] = Field(default_factory=list)

    @field_validator("payment_method", mode="before")
    @classmethod
    def _lenient_payment_method(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().lower().replace(" ", "_").replace("-", "_")
            return value or None
        return value


class ReceiptExtraction(ReceiptData):
    """What the LLM must return: the document facts plus per-field confidence."""

    field_confidence: dict[str, float] = Field(
        default_factory=dict,
        description="Self-reported confidence in [0, 1] for each extracted field.",
    )

    @field_validator("field_confidence", mode="before")
    @classmethod
    def _clean_confidence(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, dict):
            return value  # let pydantic report the type error
        cleaned: dict[str, float] = {}
        for key, raw in value.items():
            if key not in CONFIDENCE_FIELDS:
                continue  # silently drop confidences for unknown fields
            try:
                score = float(raw)
            except (TypeError, ValueError):
                continue
            cleaned[key] = min(1.0, max(0.0, score))
        return cleaned

    def to_data(self) -> ReceiptData:
        return ReceiptData.model_validate(self.model_dump(exclude={"field_confidence"}))


class Severity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class ValidationIssue(BaseModel):
    """A business-rule finding on an otherwise schema-valid extraction."""

    code: str
    message: str
    severity: Severity
    fields: list[str] = Field(default_factory=list)


class CallRecord(BaseModel):
    """One LLM call: the unit of cost and latency accounting."""

    provider: str
    model: str
    attempt: int
    purpose: Literal["extract", "repair"]
    status: Literal["ok", "invalid_json", "schema_error", "provider_error"]
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    latency_ms: float
    error: str | None = None


class UsageSummary(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: float


class ExtractionResult(BaseModel):
    """Service response: the document (if any), review decision and accounting."""

    document: ReceiptExtraction | None
    schema_valid: bool
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    attempts: int
    used_fallback: bool = False
    first_attempt_schema_valid: bool = False
    usage: UsageSummary
    calls: list[CallRecord] = Field(default_factory=list)
