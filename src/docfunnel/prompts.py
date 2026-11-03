"""Prompt templates and robust parsing of model output."""

from __future__ import annotations

import json
import re
from functools import cache
from typing import Any

from pydantic import ValidationError

from docfunnel.schema import CONFIDENCE_FIELDS, ReceiptExtraction

PROMPT_VERSION = "v1"

DOCUMENT_OPEN = "<document>"
DOCUMENT_CLOSE = "</document>"
REPAIR_MARKER = "Your previous answer could not be used."

_SYSTEM_TEMPLATE = """\
You extract structured data from receipts and invoices.

Return ONLY a JSON object that conforms to this JSON Schema (no prose, no markdown):
{schema}

Rules:
- Extract only what is printed on the document. If a field is not present, use null.
  Never infer or invent a tax ID, document number, payment method or line item.
- date: ISO 8601 (YYYY-MM-DD). Use the currency and locale of the document to resolve
  ambiguous numeric dates (e.g. 03/04/2024 is 3 April in Brazil, March 4 in the US).
- currency: ISO 4217 code (USD, EUR, GBP, BRL, ...).
- Amounts: JSON numbers with a dot as decimal separator, no currency symbols.
- subtotal is the amount before tax; tax is the total tax amount; total is the amount due.
- line_items: one entry per purchased item, with the printed line total.
- field_confidence: a number in [0, 1] for each of {fields} that reflects how sure you
  are the value is correct (lower it for blurry, ambiguous or inferred values).
"""

_REPAIR_TEMPLATE = """\
{marker}
Problems found:
{errors}

Previous answer:
{previous}

Return ONLY the corrected JSON object for the same document, conforming to the schema."""


@cache
def system_prompt() -> str:
    schema = json.dumps(
        ReceiptExtraction.model_json_schema(mode="serialization"), separators=(",", ":")
    )
    return _SYSTEM_TEMPLATE.format(schema=schema, fields=", ".join(CONFIDENCE_FIELDS))


OUTPUT_SCHEMA_NAME = "receipt_extraction"

# Keywords that OpenAI strict Structured Outputs, Anthropic structured outputs and Gemini
# ``response_json_schema`` all accept. Everything else (``title``, ``default``,
# ``minLength``, ``$ref``...) is dropped or inlined; pydantic still enforces the full
# schema on the answer, and a violation goes through the normal repair turn.
_COPIED_KEYWORDS = frozenset({"type", "enum", "description"})
_PORTABLE_FORMATS = frozenset({"date", "date-time"})


def _strict(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if isinstance(ref, str):
        resolved = _strict(defs[ref.rsplit("/", 1)[-1]], defs)
        # Keep a description written next to the $ref (pydantic puts field docs there).
        if "description" in node:
            resolved["description"] = node["description"]
        return resolved
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":
            out[key] = {name: _strict(child, defs) for name, child in value.items()}
        elif key == "items":
            out[key] = _strict(value, defs)
        elif key == "anyOf":
            out[key] = [_strict(variant, defs) for variant in value]
        elif key in _COPIED_KEYWORDS or (key == "format" and value in _PORTABLE_FORMATS):
            out[key] = value
    if out.get("type") == "object":
        # Strict modes need every property listed as required and no extra keys;
        # optional fields are expressed as ``anyOf [..., null]`` instead.
        out["required"] = list(out.get("properties", {}))
        out["additionalProperties"] = False
    return out


@cache
def _output_schema() -> str:
    source = ReceiptExtraction.model_json_schema(mode="serialization")
    schema = _strict(source, source.get("$defs", {}))
    # A free-form ``dict[str, float]`` is not allowed in strict mode: spell out one
    # nullable score per scored field instead (null = the field is not on the document).
    confidence = {"anyOf": [{"type": "number"}, {"type": "null"}]}
    schema["properties"]["field_confidence"] = {
        "type": "object",
        "description": "Confidence in [0, 1] per field; null when the field is not present.",
        "properties": {name: dict(confidence) for name in CONFIDENCE_FIELDS},
        "required": list(CONFIDENCE_FIELDS),
        "additionalProperties": False,
    }
    return json.dumps(schema)


def output_schema() -> dict[str, Any]:
    """The extraction schema in the JSON Schema subset all three providers enforce natively.

    Adapters send it as a decoding constraint (OpenAI ``json_schema``, Anthropic
    ``output_config.format``, Gemini ``response_json_schema``) on models whose
    capability profile allows it. A fresh copy is returned on every call.
    """
    schema: dict[str, Any] = json.loads(_output_schema())
    return schema


def user_prompt(document_text: str) -> str:
    return (
        f"Extract the data from this document.\n{DOCUMENT_OPEN}\n{document_text}\n{DOCUMENT_CLOSE}"
    )


def repair_prompt(previous_output: str, errors: list[str]) -> str:
    bullet_list = "\n".join(f"- {error}" for error in errors[:20])
    return _REPAIR_TEMPLATE.format(
        marker=REPAIR_MARKER, errors=bullet_list, previous=previous_output[:4000]
    )


class OutputParseError(ValueError):
    """The model output is not a JSON object."""


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from model output.

    Tolerates markdown fences and prose around the object - common, harmless
    deviations that are cheaper to fix in code than with another LLM call.
    """
    candidates: list[str] = [match.strip() for match in _FENCE.findall(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    candidates.append(text.strip())

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed
        last_error = OutputParseError(f"expected a JSON object, got {type(parsed).__name__}")
    raise OutputParseError(f"no valid JSON object found: {last_error}")


def format_validation_errors(error: ValidationError) -> list[str]:
    """Compact, model-readable rendering of pydantic errors for the repair prompt."""
    messages = []
    for item in error.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "<root>"
        messages.append(f"{location}: {item['msg']}")
    return messages
