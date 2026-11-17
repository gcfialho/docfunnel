"""Native file input: what each adapter sends when a request carries attachments."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest

from docfunnel.providers.base import Attachment, CompletionRequest, Message, ProviderError
from docfunnel.providers.replay import request_key

PDF = Attachment(b"%PDF-1.7 tiny", "application/pdf")
PNG = Attachment(b"\x89PNG\r\n\x1a\n...", "image/png")


def request(*attachments: Attachment) -> CompletionRequest:
    return CompletionRequest(
        model="some-model",
        messages=(Message("system", "SYSTEM"), Message("user", "Extract it.")),
        attachments=attachments,
    )


def test_anthropic_puts_documents_and_images_before_the_text() -> None:
    pytest.importorskip("anthropic")
    from docfunnel.providers.anthropic_provider import AnthropicProvider

    params = AnthropicProvider.build_params(request(PDF, PNG))
    content = next(iter(params["messages"]))["content"]
    assert isinstance(content, list)
    document, image, text = content
    assert document["type"] == "document"
    assert document["source"] == {
        "type": "base64",
        "media_type": "application/pdf",
        "data": base64.standard_b64encode(PDF.data).decode(),
    }
    assert image["type"] == "image"
    assert image["source"]["media_type"] == "image/png"
    assert text == {"type": "text", "text": "Extract it."}


def test_anthropic_rejects_unsupported_file_types() -> None:
    pytest.importorskip("anthropic")
    from docfunnel.providers.anthropic_provider import AnthropicProvider

    with pytest.raises(ProviderError, match="cannot take 'image/tiff'") as info:
        AnthropicProvider.build_params(request(Attachment(b"II*\x00", "image/tiff")))
    assert not info.value.retryable


def test_gemini_puts_files_before_the_text(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("google.genai")
    from docfunnel.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider(api_key="test-key")
    captured: dict[str, Any] = {}

    def generate_content(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(
            text="{}",
            usage_metadata=SimpleNamespace(
                prompt_token_count=1, candidates_token_count=1, thoughts_token_count=0
            ),
        )

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(provider, "_client", client)
    provider.complete(request(PDF))
    parts = captured["contents"][0].parts
    assert parts[0].inline_data.mime_type == "application/pdf"
    assert parts[0].inline_data.data == PDF.data
    assert parts[1].text == "Extract it."


def test_openai_refuses_attachments() -> None:
    pytest.importorskip("openai")
    from docfunnel.providers.openai_provider import OpenAIProvider

    with pytest.raises(ProviderError, match="does not send attachments") as info:
        OpenAIProvider(api_key="test-key").complete(request(PDF))
    assert not info.value.retryable


def test_replay_keys_depend_on_the_attached_bytes() -> None:
    text_only = request()
    assert request_key(text_only) == request_key(request())
    assert request_key(request(PDF)) != request_key(text_only)
    other = Attachment(b"%PDF-1.7 other", "application/pdf")
    assert request_key(request(PDF)) != request_key(request(other))


def test_model_variants_change_the_profile_not_the_model_sent() -> None:
    from docfunnel.extract.pricing import PriceTable
    from docfunnel.providers.capabilities import anthropic_model, base_model, gemini_model

    variant = "gemini-3.8-flash+thinking_level=medium+structured_outputs=false"
    profile = gemini_model(variant)
    assert profile.thinking_level == "medium"
    assert profile.structured_outputs is False
    assert profile.min_output_tokens == gemini_model("gemini-3.8-flash").min_output_tokens
    assert anthropic_model("claude-haiku-5-5+effort=none").effort is None
    assert base_model(variant) == "gemini-3.8-flash"
    prices = PriceTable.load()
    assert prices.cost(variant, 10**6, 0) == prices.cost("gemini-3.8-flash", 10**6, 0)
    with pytest.raises(ValueError, match="key=value with key in"):
        gemini_model("gemini-3.8-flash+temperature=0")

    pytest.importorskip("anthropic")
    from docfunnel.providers.anthropic_provider import AnthropicProvider

    params = AnthropicProvider.build_params(
        CompletionRequest(
            model="claude-haiku-5-5+effort=medium",
            messages=(Message("system", "S"), Message("user", "U")),
        )
    )
    assert params["model"] == "claude-haiku-5-5"
    assert params["output_config"]["effort"] == "medium"
