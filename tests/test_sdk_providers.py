"""Real-provider adapters tested against stubbed SDK clients (no network, no keys).

These pin down the request mapping (system prompt placement, JSON mode, token
accounting) and the retryable/non-retryable error classification.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, NoReturn

import pytest

from docfunnel.providers.base import CompletionRequest, Message, ProviderError

if TYPE_CHECKING:
    from docfunnel.providers.anthropic_provider import AnthropicProvider
    from docfunnel.providers.gemini_provider import GeminiProvider
    from docfunnel.providers.openai_provider import OpenAIProvider

REQUEST = CompletionRequest(
    model="some-model",
    messages=(
        Message("system", "SYSTEM"),
        Message("user", "USER"),
        Message("assistant", "PREVIOUS"),
        Message("user", "REPAIR"),
    ),
    max_output_tokens=512,
)


def make_error(cls: type[Exception], **attrs: Any) -> Exception:
    """Instantiate an SDK exception without its version-specific constructor."""
    error = cls.__new__(cls)
    Exception.__init__(error, "boom")
    for key, value in attrs.items():
        setattr(error, key, value)
    return error


def raiser(error: Exception) -> Callable[..., NoReturn]:
    def fail(**_: Any) -> NoReturn:
        raise error

    return fail


class TestOpenAI:
    @pytest.fixture
    def provider(self) -> OpenAIProvider:
        pytest.importorskip("openai")
        from docfunnel.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key="test-key")

    def test_request_mapping_and_usage(
        self, provider: OpenAIProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                model="some-model-2025",
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"total": 1}'))],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
            )

        monkeypatch.setattr(
            provider,
            "_client",
            SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        )
        response = provider.complete(REQUEST)

        assert [m["role"] for m in captured["messages"]] == ["system", "user", "assistant", "user"]
        assert captured["response_format"] == {"type": "json_object"}
        assert captured["temperature"] == 0.0
        assert (response.text, response.input_tokens, response.output_tokens) == (
            '{"total": 1}',
            11,
            7,
        )

    @pytest.mark.parametrize(
        ("error_name", "retryable"),
        [
            ("RateLimitError", True),
            ("APIConnectionError", True),
            ("InternalServerError", True),
            ("BadRequestError", False),
        ],
    )
    def test_error_classification(
        self,
        provider: OpenAIProvider,
        monkeypatch: pytest.MonkeyPatch,
        error_name: str,
        retryable: bool,
    ) -> None:
        import openai

        error = make_error(getattr(openai, error_name))
        monkeypatch.setattr(
            provider,
            "_client",
            SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=raiser(error)))
            ),
        )
        with pytest.raises(ProviderError) as info:
            provider.complete(REQUEST)
        assert info.value.retryable is retryable


class TestAnthropic:
    @pytest.fixture
    def provider(self) -> AnthropicProvider:
        pytest.importorskip("anthropic")
        from docfunnel.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key="test-key")

    def test_system_prompt_is_passed_separately(
        self, provider: AnthropicProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                model="some-model",
                content=[SimpleNamespace(type="text", text='{"total": 1}')],
                usage=SimpleNamespace(input_tokens=20, output_tokens=5),
            )

        monkeypatch.setattr(
            provider, "_client", SimpleNamespace(messages=SimpleNamespace(create=create))
        )
        response = provider.complete(REQUEST)

        assert captured["system"] == "SYSTEM"
        assert [m["role"] for m in captured["messages"]] == ["user", "assistant", "user"]
        assert captured["max_tokens"] == 512
        assert (response.input_tokens, response.output_tokens) == (20, 5)

    @pytest.mark.parametrize(("status", "retryable"), [(429, True), (529, True), (400, False)])
    def test_error_classification(
        self,
        provider: AnthropicProvider,
        monkeypatch: pytest.MonkeyPatch,
        status: int,
        retryable: bool,
    ) -> None:
        import anthropic

        error = make_error(anthropic.APIStatusError, status_code=status)
        monkeypatch.setattr(
            provider, "_client", SimpleNamespace(messages=SimpleNamespace(create=raiser(error)))
        )
        with pytest.raises(ProviderError) as info:
            provider.complete(REQUEST)
        assert info.value.retryable is retryable


class TestGemini:
    @pytest.fixture
    def provider(self) -> GeminiProvider:
        pytest.importorskip("google.genai")
        from docfunnel.providers.gemini_provider import GeminiProvider

        return GeminiProvider(api_key="test-key")

    def test_roles_and_json_mime_type(
        self, provider: GeminiProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def generate_content(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                text='{"total": 1}',
                usage_metadata=SimpleNamespace(prompt_token_count=30, candidates_token_count=4),
            )

        monkeypatch.setattr(
            provider,
            "_client",
            SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)),
        )
        response = provider.complete(REQUEST)

        assert [c.role for c in captured["contents"]] == ["user", "model", "user"]
        assert captured["config"].system_instruction == "SYSTEM"
        assert captured["config"].response_mime_type == "application/json"
        assert (response.input_tokens, response.output_tokens) == (30, 4)

    @pytest.mark.parametrize(("code", "retryable"), [(429, True), (503, True), (400, False)])
    def test_error_classification(
        self, provider: GeminiProvider, monkeypatch: pytest.MonkeyPatch, code: int, retryable: bool
    ) -> None:
        from google.genai import errors

        error = make_error(errors.APIError, code=code)
        monkeypatch.setattr(
            provider,
            "_client",
            SimpleNamespace(models=SimpleNamespace(generate_content=raiser(error))),
        )
        with pytest.raises(ProviderError) as info:
            provider.complete(REQUEST)
        assert info.value.retryable is retryable
