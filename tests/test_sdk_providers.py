"""Real-provider adapters tested against stubbed SDK clients (no network, no keys).

These pin down the request each adapter builds per model (system prompt placement,
structured output vs JSON mode, reasoning/thinking controls, token limits), token
accounting, and the retryable/non-retryable error classification.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, NoReturn

import pytest

from docfunnel.prompts import output_schema
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
SCHEMA = output_schema()


def request_for(model: str, *, max_output_tokens: int = 2048) -> CompletionRequest:
    """What the extractor sends: the schema attached, temperature 0 requested."""
    return CompletionRequest(
        model=model,
        messages=(Message("system", "SYSTEM"), Message("user", "USER")),
        max_output_tokens=max_output_tokens,
        response_schema=SCHEMA,
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

    @staticmethod
    def stub(
        provider: OpenAIProvider, monkeypatch: pytest.MonkeyPatch, message: Any
    ) -> dict[str, Any]:
        captured: dict[str, Any] = {}

        def create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                model="some-model-2025",
                choices=[SimpleNamespace(message=message)],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
            )

        monkeypatch.setattr(
            provider,
            "_client",
            SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        )
        return captured

    def test_request_mapping_and_usage(
        self, provider: OpenAIProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = self.stub(
            provider,
            monkeypatch,
            SimpleNamespace(content='{"total": 1}', refusal=None),
        )
        response = provider.complete(REQUEST)

        assert [m["role"] for m in captured["messages"]] == ["system", "user", "assistant", "user"]
        assert captured["max_completion_tokens"] == 512
        assert (response.text, response.input_tokens, response.output_tokens) == (
            '{"total": 1}',
            11,
            7,
        )

    def test_unknown_model_gets_the_safe_default(self) -> None:
        from docfunnel.providers.openai_provider import OpenAIProvider

        params = OpenAIProvider.build_params(request_for("some-future-model"))

        # JSON mode without a schema, no sampling or reasoning parameters.
        assert params["response_format"] == {"type": "json_object"}
        assert "temperature" not in params
        assert "reasoning_effort" not in params
        assert "max_tokens" not in params

    @pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6.1-terra"])
    def test_gpt6_reasoning_models(self, model: str) -> None:
        from docfunnel.providers.openai_provider import OpenAIProvider

        params = OpenAIProvider.build_params(request_for(model))

        assert params["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "receipt_extraction", "schema": SCHEMA, "strict": True},
        }
        assert "temperature" not in params  # only allowed at effort "none"; never sent
        assert "max_tokens" not in params

    def test_gpt6_luna_runs_without_reasoning(self) -> None:
        from docfunnel.providers.openai_provider import OpenAIProvider

        params = OpenAIProvider.build_params(request_for("gpt-6-luna"))

        assert params["reasoning_effort"] == "none"
        assert params["max_completion_tokens"] == 4096

    def test_gpt61_terra_reasons_a_little_with_headroom(self) -> None:
        from docfunnel.providers.openai_provider import OpenAIProvider

        params = OpenAIProvider.build_params(request_for("gpt-6.1-terra"))

        assert params["reasoning_effort"] == "low"
        assert params["max_completion_tokens"] == 16_000

    @pytest.mark.parametrize("model", ["gpt-4o-mini", "gpt-4.1-mini"])
    def test_older_models_keep_temperature_and_get_structured_outputs(self, model: str) -> None:
        from docfunnel.providers.openai_provider import OpenAIProvider

        params = OpenAIProvider.build_params(request_for(model))

        assert params["temperature"] == 0.0
        assert "reasoning_effort" not in params
        assert params["max_completion_tokens"] == 2048
        assert params["response_format"]["type"] == "json_schema"

    def test_larger_requested_limit_wins_over_the_floor(self) -> None:
        from docfunnel.providers.openai_provider import OpenAIProvider

        params = OpenAIProvider.build_params(request_for("gpt-6-luna", max_output_tokens=9000))

        assert params["max_completion_tokens"] == 9000

    def test_json_mode_off_sends_no_response_format(self) -> None:
        from dataclasses import replace

        from docfunnel.providers.openai_provider import OpenAIProvider

        params = OpenAIProvider.build_params(replace(request_for("gpt-6-luna"), json_mode=False))

        assert "response_format" not in params

    def test_refusal_is_not_retryable(
        self, provider: OpenAIProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.stub(
            provider, monkeypatch, SimpleNamespace(content=None, refusal="I can't help with that.")
        )
        with pytest.raises(ProviderError, match="refusal") as info:
            provider.complete(request_for("gpt-6-luna"))
        assert info.value.retryable is False

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

    @staticmethod
    def stub(
        provider: AnthropicProvider,
        monkeypatch: pytest.MonkeyPatch,
        *,
        content: list[Any],
        stop_reason: str = "end_turn",
    ) -> dict[str, Any]:
        captured: dict[str, Any] = {}

        def create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                model="some-model",
                content=content,
                stop_reason=stop_reason,
                usage=SimpleNamespace(input_tokens=20, output_tokens=5),
            )

        monkeypatch.setattr(
            provider, "_client", SimpleNamespace(messages=SimpleNamespace(create=create))
        )
        return captured

    def test_system_prompt_is_passed_separately(
        self, provider: AnthropicProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = self.stub(
            provider, monkeypatch, content=[SimpleNamespace(type="text", text='{"total": 1}')]
        )
        response = provider.complete(REQUEST)

        assert captured["system"] == "SYSTEM"
        assert [m["role"] for m in captured["messages"]] == ["user", "assistant", "user"]
        assert captured["max_tokens"] == 512
        assert "temperature" not in captured  # API version 2026-10-21 rejects it
        assert (response.input_tokens, response.output_tokens) == (20, 5)

    def test_haiku_5_5_thinking_off_low_effort_structured_output(self) -> None:
        from docfunnel.providers.anthropic_provider import AnthropicProvider

        params = AnthropicProvider.build_params(request_for("claude-haiku-5-5"))

        assert params["thinking"] == {"type": "disabled"}
        assert params["output_config"] == {
            "effort": "low",
            "format": {"type": "json_schema", "schema": SCHEMA},
        }
        assert params["max_tokens"] == 4096
        assert "temperature" not in params

    def test_haiku_4_5_gets_structured_output_but_no_effort_or_thinking(self) -> None:
        from docfunnel.providers.anthropic_provider import AnthropicProvider

        params = AnthropicProvider.build_params(request_for("claude-haiku-4-5"))

        assert params["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
        assert "thinking" not in params  # effort errors on Haiku 4.5; thinking is off
        assert params["max_tokens"] == 2048

    @pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"])
    def test_models_that_cannot_disable_thinking_lower_effort_instead(self, model: str) -> None:
        from docfunnel.providers.anthropic_provider import AnthropicProvider

        params = AnthropicProvider.build_params(request_for(model))

        assert "thinking" not in params  # {"type": "disabled"} returns 400 on these
        assert params["output_config"]["effort"] == "low"
        assert params["max_tokens"] == 8192

    def test_unknown_model_gets_structured_output_only(self) -> None:
        from docfunnel.providers.anthropic_provider import AnthropicProvider

        params = AnthropicProvider.build_params(request_for("claude-future-1"))

        assert params["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
        assert "thinking" not in params

    def test_no_schema_means_no_output_config(self) -> None:
        from docfunnel.providers.anthropic_provider import AnthropicProvider

        params = AnthropicProvider.build_params(REQUEST)

        assert "output_config" not in params

    def test_thinking_blocks_are_skipped_when_reading_the_answer(
        self, provider: AnthropicProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.stub(
            provider,
            monkeypatch,
            content=[
                SimpleNamespace(type="thinking", thinking="", signature="sig"),
                SimpleNamespace(type="text", text='{"total": 1}'),
            ],
        )
        assert provider.complete(request_for("claude-sonnet-5-5")).text == '{"total": 1}'

    def test_refusal_is_not_retryable(
        self, provider: AnthropicProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.stub(provider, monkeypatch, content=[], stop_reason="refusal")
        with pytest.raises(ProviderError, match="refusal") as info:
            provider.complete(request_for("claude-haiku-5-5"))
        assert info.value.retryable is False

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
