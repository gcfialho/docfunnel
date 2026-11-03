"""The HTTP body each real SDK sends for the default models, captured offline.

The SDK clients run for real on top of an ``httpx.MockTransport``: this checks that
the installed SDK accepts every argument the adapters pass and shows the JSON that
would go over the wire. It says nothing about whether the live API accepts it.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from docfunnel.prompts import output_schema
from docfunnel.providers.base import CompletionRequest, Message

REQUEST_MESSAGES = (Message("system", "SYSTEM"), Message("user", "USER"))


def capture(response_body: dict[str, Any]) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response_body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def capture_httpx2(response_body: dict[str, Any]) -> tuple[Any, list[Any]]:
    """Same as :func:`capture` for the anthropic SDK, which is built on ``httpx2``."""
    httpx2 = pytest.importorskip("httpx2")
    seen: list[Any] = []

    def handler(request: Any) -> Any:
        seen.append(request)
        return httpx2.Response(200, json=response_body)

    return httpx2.Client(transport=httpx2.MockTransport(handler)), seen


def request_for(model: str) -> CompletionRequest:
    return CompletionRequest(
        model=model, messages=REQUEST_MESSAGES, response_schema=output_schema()
    )


def test_openai_gpt_6_luna_wire_body(monkeypatch: pytest.MonkeyPatch) -> None:
    openai = pytest.importorskip("openai")
    from docfunnel.providers.openai_provider import OpenAIProvider

    http, seen = capture(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-6-luna",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": '{"total": 1}', "refusal": None},
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        }
    )
    provider = OpenAIProvider(api_key="test-key")
    monkeypatch.setattr(
        provider, "_client", openai.OpenAI(api_key="test-key", http_client=http, max_retries=0)
    )

    response = provider.complete(request_for("gpt-6-luna"))

    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/chat/completions"
    assert body["model"] == "gpt-6-luna"
    assert body["reasoning_effort"] == "none"
    assert body["max_completion_tokens"] == 4096
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == output_schema()
    assert not {"temperature", "max_tokens", "top_p"} & set(body)
    assert (response.text, response.output_tokens) == ('{"total": 1}', 3)


def test_anthropic_claude_haiku_5_5_wire_body(monkeypatch: pytest.MonkeyPatch) -> None:
    anthropic = pytest.importorskip("anthropic")
    from docfunnel.providers.anthropic_provider import AnthropicProvider

    http, seen = capture_httpx2(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": '{"total": 1}'}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 12, "output_tokens": 3},
        }
    )
    provider = AnthropicProvider(api_key="test-key")
    monkeypatch.setattr(
        provider,
        "_client",
        anthropic.Anthropic(api_key="test-key", http_client=http, max_retries=0),
    )

    response = provider.complete(request_for("claude-haiku-5-5"))

    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/messages"
    assert seen[0].headers["anthropic-version"] == "2026-10-21"
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == 8192
    assert body["system"] == "SYSTEM"
    assert "thinking" not in body
    assert body["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": output_schema()},
    }
    assert not {"temperature", "top_p", "top_k"} & set(body)
    assert (response.text, response.output_tokens) == ('{"total": 1}', 3)


def test_gemini_3_5_flash_lite_wire_body(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("google.genai")
    from google import genai
    from google.genai import types

    from docfunnel.providers.gemini_provider import GeminiProvider

    http, seen = capture(
        {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": '{"total": 1}'}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 12,
                "candidatesTokenCount": 3,
                "thoughtsTokenCount": 5,
            },
        }
    )
    provider = GeminiProvider(api_key="test-key")
    monkeypatch.setattr(
        provider,
        "_client",
        genai.Client(api_key="test-key", http_options=types.HttpOptions(httpx_client=http)),
    )

    response = provider.complete(request_for("gemini-3.5-flash-lite"))

    body = json.loads(seen[0].content)
    assert seen[0].url.path.endswith("/models/gemini-3.5-flash-lite:generateContent")
    config = body["generationConfig"]
    # The SDK copies the sub-object as is; the API's proto3 JSON accepts both spellings.
    assert config["thinkingConfig"] == {"thinking_level": "MINIMAL"}
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == output_schema()
    assert config["maxOutputTokens"] == 8192
    assert "temperature" not in config
    assert body["systemInstruction"]["parts"] == [{"text": "SYSTEM"}]
    assert (response.text, response.output_tokens) == ('{"total": 1}', 8)
