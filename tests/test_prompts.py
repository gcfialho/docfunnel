import json

import pytest

from docfunnel.prompts import (
    DOCUMENT_OPEN,
    REPAIR_MARKER,
    OutputParseError,
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
