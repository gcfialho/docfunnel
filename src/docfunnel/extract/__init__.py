"""LLM extraction stage: schema, normalization, business rules, prompts and the extractor.

The :class:`Extractor` sends a document to a provider, parses and validates the JSON,
repairs schema errors, retries transient failures, walks a fallback chain, applies
business rules and records tokens, cost and latency for every call.
"""

from docfunnel.extract.extractor import Extractor, ModelTarget, RetryPolicy
from docfunnel.extract.pricing import PriceTable
from docfunnel.extract.schema import (
    CallRecord,
    ExtractionResult,
    LineItem,
    PaymentMethod,
    ReceiptData,
    ReceiptExtraction,
)
from docfunnel.extract.validation import ReviewPolicy, check_business_rules, review_decision

__all__ = [
    "CallRecord",
    "ExtractionResult",
    "Extractor",
    "LineItem",
    "ModelTarget",
    "PaymentMethod",
    "PriceTable",
    "ReceiptData",
    "ReceiptExtraction",
    "RetryPolicy",
    "ReviewPolicy",
    "check_business_rules",
    "review_decision",
]
