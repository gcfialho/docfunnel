import json
from collections.abc import Iterator
from typing import Any

import pytest

from docfunnel.prompts import (
    DOCUMENT_OPEN,
    REPAIR_MARKER,
    OutputParseError,
    output_schema,
    parse_json_object,
    repair_prompt,
    system_prompt,
    user_prompt,
)


@pytest.mark.parametrize(
    "text",
    [
        '{"total": 1}',
        '```json\n{"total": 1}\n```',
        'Sure! Here is the JSON:\n{"total": 1}\nLet me know if you need more.',
        '```\n{"total": 1}\n```',
    ],
)
def test_parse_json_object_tolerates_wrapping(text: str) -> None:
    assert parse_json_object(text) == {"total": 1}


@pytest.mark.parametrize("text", ['{"total": 1', "[1, 2]", "no json here", ""])
def test_parse_json_object_rejects_invalid(text: str) -> None:
    with pytest.raises(OutputParseError):
        parse_json_object(text)


def test_system_prompt_embeds_schema() -> None:
    prompt = system_prompt()
    schema_start = prompt.index("{")
    assert '"line_items"' in prompt
    assert "null" in prompt
    json.loads(prompt[schema_start : prompt.index("\n", schema_start)])


def test_user_and_repair_prompts() -> None:
    assert DOCUMENT_OPEN in user_prompt("TOTAL 1.00")
    repair = repair_prompt('{"total": "x"}', ["total: not a number"])
    assert REPAIR_MARKER in repair
    assert "- total: not a number" in repair


def _nodes(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("properties", {}).values():
        yield from _nodes(child)
    if "items" in node:
        yield from _nodes(node["items"])
    for variant in node.get("anyOf", []):
        yield from _nodes(variant)


def test_output_schema_uses_the_strict_portable_subset() -> None:
    schema = output_schema()
    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "anyOf",
        "description",
        "format",
    }
    assert schema["type"] == "object"  # the root may not be anyOf (OpenAI strict mode)
    for node in _nodes(schema):
        assert set(node) <= allowed, set(node) - allowed
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert node["required"] == list(node["properties"])
    assert "$defs" not in json.dumps(schema)


def test_output_schema_spells_out_confidence_and_inlines_definitions() -> None:
    props = output_schema()["properties"]
    assert set(props["field_confidence"]["properties"]) == {
        "vendor_name",
        "vendor_tax_id",
        "document_number",
        "date",
        "currency",
        "subtotal",
        "tax",
        "total",
        "payment_method",
        "line_items",
    }
    method = props["payment_method"]["anyOf"]
    assert method[0]["enum"] == ["cash", "card", "bank_transfer", "pix", "other"]
    assert method[1] == {"type": "null"}
    line_item = props["line_items"]["items"]
    assert line_item["required"] == ["description", "quantity", "unit_price", "total"]
    assert props["date"]["anyOf"][0] == {"format": "date", "type": "string"}


def test_output_schema_returns_an_independent_copy() -> None:
    output_schema()["properties"].clear()
    assert output_schema()["properties"]


def test_an_answer_shaped_by_the_output_schema_validates() -> None:
    from docfunnel.schema import CONFIDENCE_FIELDS, ReceiptExtraction

    answer: dict[str, Any] = dict.fromkeys(output_schema()["properties"])
    answer["line_items"] = [
        {"description": "Coffee", "quantity": None, "unit_price": None, "total": 3.5}
    ]
    answer["total"] = 3.5
    confidence: dict[str, float | None] = dict.fromkeys(CONFIDENCE_FIELDS)
    answer["field_confidence"] = confidence | {"total": 0.9}

    document = ReceiptExtraction.model_validate(answer)

    assert document.field_confidence == {"total": 0.9}  # nulls are dropped
