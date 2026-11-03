"""Shared test helpers (importable from test modules, unlike conftest)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from docfunnel.providers.base import CompletionRequest, CompletionResponse, ProviderError

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPO_ROOT / "data" / "synthetic" / "receipts.jsonl"

US_RECEIPT = """\
         MAPLE STREET HARDWARE
      910 Elm Rd, Austin, TX 78701
Receipt # 924402
Date: 2023-08-26 16:41
----------------------------------------
3 x Iced Tea                       $8.25
Hammer 16oz                       $18.99
----------------------------------------
Subtotal                          $27.24
Sales Tax (8%)                     $2.18
TOTAL                             $29.42
Paid by: CASH
"""

VALID_PAYLOAD = {
    "vendor_name": "Maple Street Hardware",
    "vendor_tax_id": None,
    "document_number": "924402",
    "date": "2023-08-26",
    "currency": "USD",
    "subtotal": 27.24,
    "tax": 2.18,
    "total": 29.42,
    "payment_method": "cash",
    "line_items": [
        {"description": "Iced Tea", "quantity": 3, "unit_price": 2.75, "total": 8.25},
        {"description": "Hammer 16oz", "quantity": 1, "unit_price": 18.99, "total": 18.99},
    ],
    "field_confidence": {"vendor_name": 0.95, "total": 0.99, "date": 0.97},
}


class ScriptedProvider:
    """Returns pre-programmed outputs (str) or raises pre-programmed errors, in order."""

    def __init__(self, script: Iterable[str | Exception], name: str = "scripted") -> None:
        self.script = list(script)
        self.name = name
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        if not self.script:
            raise ProviderError("script exhausted", retryable=False)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return CompletionResponse(
            text=item, model=request.model, input_tokens=1000, output_tokens=200
        )
