"""A deterministic, offline stand-in for an LLM.

``FakeProvider`` is **not** a model. It is a rule-based receipt parser wrapped in the
same interface as the real providers, plus *deterministic fault injection* so the
rest of the system (JSON repair, schema retries, fallback, review routing, eval
metrics) can be exercised in CI without API keys or network.

Two model names are understood:

* ``fake-mini`` - injects malformed JSON, schema violations, hard failures and
  confident hallucinations at fixed rates (like a small, cheap model);
* ``fake-pro`` - no format faults and a lower hallucination rate (a fallback model).

Fault decisions are a pure function of (model, fault kind, document text), so every
run produces identical outputs. Nothing about its accuracy says anything about any
real LLM.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from docfunnel.normalize import parse_amount, parse_date
from docfunnel.prompts import DOCUMENT_CLOSE, DOCUMENT_OPEN, REPAIR_MARKER
from docfunnel.providers.base import (
    CompletionRequest,
    CompletionResponse,
    ProviderError,
    estimate_tokens,
)


@dataclass(frozen=True)
class FaultProfile:
    malformed_json: float = 0.0  # first answer is truncated / not JSON
    schema_violation: float = 0.0  # first answer is JSON but violates the schema
    hallucination: float = 0.0  # a field absent from the document is filled in
    hard_failure: float = 0.0  # every answer for this document is unusable
    fenced_output: float = 0.3  # harmless: answer wrapped in a ```json fence


FAULT_PROFILES: dict[str, FaultProfile] = {
    "fake-mini": FaultProfile(
        malformed_json=0.10, schema_violation=0.06, hallucination=0.15, hard_failure=0.04
    ),
    "fake-pro": FaultProfile(hallucination=0.02),
}

_AMOUNT = re.compile(r"-?(?:\d{1,3}(?:[.,]\d{3})+|\d+)[.,]\d{2}(?!\d)")
_NOISE = re.compile(r"[A-Za-z][0-9]|[0-9][A-Za-z]")
_SEPARATOR = re.compile(r"^\s*[-=]{10,}\s*$")
_POS_ITEM = re.compile(
    r"^(?:(?P<qty>\d+)\s*[xX]\s+)?(?P<desc>.+?)\s+"
    r"(?P<amt>(?:R\$|US\$|[$£])?\s?\d[\d.,]*[.,]\d{2}(?:\s?€)?)\s*$"
)
_DOC_NUMBER = re.compile(
    r"\b(?:receipt|invoice|rechnung|bon|cupom|nota)[\s-]*(?:#|no\.?|nr\.?|nº|n°|number)\s*:?\s*"
    r"(?P<num>[A-Z0-9][\w/-]*\d[\w/-]*)",
    re.IGNORECASE,
)
_TAX_ID = re.compile(
    r"^\s*(?:tax\s*id|ein|vat\s*reg(?:istration)?\s*no|vat\s*no|ust-idnr|cnpj)\.?\s*:?\s*(?P<id>.+)$",
    re.IGNORECASE,
)
_DATES = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]\d{4}\b"),
    re.compile(r"\b\d{1,2} [A-Z][a-z]{2} \d{4}\b"),
    re.compile(r"\b[A-Z][a-z]{2} \d{1,2}, \d{4}\b"),
)
_HEADER_WORDS = {"invoice", "tax invoice", "receipt", "rechnung", "nota fiscal de serviço"}
_SUBTOTAL_WORDS = ("subtotal", "sub-total", "zwischensumme", "net", "netto")
_TAX_WORDS = ("tax", "vat", "mwst", "ust", "iss", "imposto")
_TOTAL_WORDS = ("total", "summe", "gesamtbetrag", "amount due")
_PAYMENT_LABELS = ("paid by", "payment", "zahlung", "pagamento")
_PAYMENT_KEYWORDS: tuple[tuple[str, str], ...] = (
    (r"\bpix\b", "pix"),
    (r"transfer|überweisung|bacs|\bwire\b|iban", "bank_transfer"),
    (r"visa|mastercard|card|karte|cartão", "card"),
    (r"\bcash\b|\bbar\b|dinheiro", "cash"),
)
_LABEL_DENOISE = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b"})


def _denoise_label(text: str) -> str:
    """Undo look-alike digit substitutions inside words (``T0TAL`` -> ``total``)."""
    words = [
        w.translate(_LABEL_DENOISE) if any(c.isalpha() for c in w) and not _AMOUNT.search(w) else w
        for w in text.split()
    ]
    return " ".join(words).lower()


def _last_amount(line: str) -> Decimal | None:
    matches = _AMOUNT.findall(line)
    if not matches:
        return None
    try:
        return parse_amount(matches[-1])
    except ValueError:
        return None


def _detect_currency(text: str) -> str | None:
    if "R$" in text or "BRL" in text:
        return "BRL"
    if "€" in text or "EUR" in text:
        return "EUR"
    if "£" in text or "GBP" in text:
        return "GBP"
    if "$" in text or "USD" in text:
        return "USD"
    return None


def heuristic_extract(text: str) -> dict[str, Any]:
    """Rule-based extraction of a receipt/invoice into the extraction schema's shape."""
    lines = [line.rstrip() for line in text.splitlines()]
    nonempty = [line.strip() for line in lines if line.strip()]
    conf: dict[str, float] = {}
    out: dict[str, Any] = {}

    # Vendor: first meaningful line.
    vendor = next((ln for ln in nonempty if ln.lower() not in _HEADER_WORDS), None)
    if vendor:
        out["vendor_name"] = vendor.title() if vendor.isupper() else vendor
        conf["vendor_name"] = 0.5 if _NOISE.search(vendor) else 0.9

    # Currency.
    currency = _detect_currency(text)
    out["currency"] = currency
    if currency:
        conf["currency"] = 0.95

    # Tax ID and document number.
    for line in nonempty:
        match = _TAX_ID.match(line)
        if match:
            out["vendor_tax_id"] = match["id"].strip()
            conf["vendor_tax_id"] = 0.9
            break
    match = _DOC_NUMBER.search(text)
    if match:
        out["document_number"] = match["num"]
        conf["document_number"] = 0.9

    # Date: first date-looking token, ordered by the currency's locale convention.
    for pattern in _DATES:
        found = pattern.search(text)
        if not found:
            continue
        token = found.group(0)
        try:
            parsed = parse_date(token, dayfirst=currency != "USD")
        except ValueError:
            continue
        out["date"] = parsed.isoformat() if parsed else None
        parts = re.split(r"[/.]", token)
        ambiguous = len(parts) == 3 and all(p.isdigit() and int(p) <= 12 for p in parts[:2])
        conf["date"] = 0.75 if ambiguous else 0.95
        break

    # Labelled amounts (scan bottom-up so the final TOTAL wins over intermediate ones).
    for line in reversed(nonempty):
        amount = _last_amount(line)
        if amount is None:
            continue
        label = _denoise_label(_AMOUNT.sub(" ", line))
        if "subtotal" not in out and any(label.startswith(w) for w in _SUBTOTAL_WORDS):
            out["subtotal"] = amount
        elif "tax" not in out and any(re.search(rf"\b{w}\b", label) for w in _TAX_WORDS):
            out["tax"] = amount
        elif "total" not in out and any(w in label for w in _TOTAL_WORDS) and "sub" not in label:
            out["total"] = amount
    for key in ("subtotal", "tax", "total"):
        if key in out:
            conf[key] = 0.9
    if "total" not in out:
        amounts = [a for a in (_last_amount(line) for line in nonempty) if a is not None]
        if amounts:  # guess: the largest amount on the page
            out["total"] = max(amounts)
            conf["total"] = 0.4

    # Payment method from an explicitly labelled line.
    for line in nonempty:
        lowered = line.lower()
        if any(lowered.startswith(label) for label in _PAYMENT_LABELS):
            for pattern, method in _PAYMENT_KEYWORDS:
                if re.search(pattern, lowered):
                    out["payment_method"] = method
                    conf["payment_method"] = 0.85
                    break
            break

    items = _table_items(nonempty) or _pos_items(lines)
    out["line_items"] = items
    if items:
        conf["line_items"] = 0.85
        subtotal = out.get("subtotal")
        if subtotal is not None:
            items_sum = sum((Decimal(str(i["total"])) for i in items), Decimal("0"))
            if abs(items_sum - subtotal) > Decimal("0.02"):
                conf["line_items"] = 0.4

    for key in ("subtotal", "tax", "total"):
        if key in out and out[key] is not None:
            out[key] = float(out[key])
    out["field_confidence"] = conf
    return out


def _pos_items(lines: list[str]) -> list[dict[str, Any]]:
    separators = [i for i, line in enumerate(lines) if _SEPARATOR.match(line)]
    if len(separators) < 2:
        return []
    items = []
    for line in lines[separators[0] + 1 : separators[1]]:
        match = _POS_ITEM.match(line.strip())
        if not match:
            continue
        try:
            total = parse_amount(match["amt"])
        except ValueError:
            continue
        if total is None:
            continue
        qty = Decimal(match["qty"]) if match["qty"] else Decimal(1)
        items.append(
            {
                "description": match["desc"].strip(),
                "quantity": float(qty),
                "unit_price": float((total / qty).quantize(Decimal("0.01"))),
                "total": float(total),
            }
        )
    return items


def _table_items(lines: list[str]) -> list[dict[str, Any]]:
    items = []
    in_table = False
    for line in lines:
        cells = [c.strip() for c in line.split("|")]
        if len(cells) != 4:
            in_table = False
            continue
        if not in_table:
            in_table = not any(ch.isdigit() for ch in line)  # header row
            continue
        try:
            qty, unit, total = (parse_amount(c) for c in cells[1:])
        except ValueError:
            continue
        if total is None:
            continue
        items.append(
            {
                "description": cells[0],
                "quantity": float(qty) if qty is not None else None,
                "unit_price": float(unit) if unit is not None else None,
                "total": float(total),
            }
        )
    return items


_INVENTED: tuple[tuple[str, Any], ...] = (
    ("document_number", "INV-000123"),
    ("payment_method", "card"),
    ("vendor_tax_id", "12-3456789"),
    ("tax", 1.0),
)


class FakeProvider:
    """Deterministic offline provider. See module docstring."""

    name = "fake"

    def __init__(self, profiles: dict[str, FaultProfile] | None = None) -> None:
        self._profiles = profiles if profiles is not None else FAULT_PROFILES

    def _roll(self, model: str, kind: str, text: str) -> float:
        digest = hashlib.sha256(f"{model}|{kind}|{text}".encode()).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        users = [m.content for m in request.messages if m.role == "user"]
        if not users or DOCUMENT_OPEN not in users[0]:
            raise ProviderError("fake provider expects a <document> block", retryable=False)
        first = users[0]
        document = first[
            first.index(DOCUMENT_OPEN) + len(DOCUMENT_OPEN) : first.rfind(DOCUMENT_CLOSE)
        ].strip()
        is_repair = REPAIR_MARKER in users[-1]
        profile = self._profiles.get(request.model, FaultProfile(fenced_output=0.0))
        roll = lambda kind: self._roll(request.model, kind, document)  # noqa: E731

        if roll("hard_failure") < profile.hard_failure:
            text = "I'm sorry, but I can't reliably read this document."
        else:
            payload = heuristic_extract(document)
            if roll("hallucination") < profile.hallucination:
                payload = self._hallucinate(payload, roll("hallucination_field"))
            text = json.dumps(payload, ensure_ascii=False)
            if not is_repair and roll("malformed") < profile.malformed_json:
                text = "Here is the extracted data:\n```json\n" + text[: len(text) // 2]
            elif not is_repair and roll("schema") < profile.schema_violation:
                broken = dict(payload, total="see line items", line_items="n/a")
                text = json.dumps(broken, ensure_ascii=False)
            elif roll("fence") < profile.fenced_output:
                text = f"```json\n{text}\n```"

        prompt_chars = "".join(m.content for m in request.messages)
        return CompletionResponse(
            text=text,
            model=request.model,
            input_tokens=estimate_tokens(prompt_chars),
            output_tokens=estimate_tokens(text),
        )

    @staticmethod
    def _hallucinate(payload: dict[str, Any], pick: float) -> dict[str, Any]:
        empty = [(k, v) for k, v in _INVENTED if payload.get(k) is None]
        if not empty:
            return payload
        key, value = empty[int(pick * len(empty)) % len(empty)]
        confidence = dict(payload["field_confidence"], **{key: 0.85})
        return dict(payload, **{key: value}, field_confidence=confidence)
