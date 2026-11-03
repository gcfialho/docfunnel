"""OpenAI Chat Completions backend (Structured Outputs or JSON mode, per model)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from docfunnel.prompts import OUTPUT_SCHEMA_NAME
from docfunnel.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderError,
    ProviderNotConfiguredError,
)
from docfunnel.providers.capabilities import openai_model

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam
    from openai.types.chat.completion_create_params import CompletionCreateParamsNonStreaming


def _message_param(message: Message) -> ChatCompletionMessageParam:
    # One branch per role so each dict matches exactly one of the SDK's message TypedDicts.
    if message.role == "system":
        return {"role": "system", "content": message.content}
    if message.role == "user":
        return {"role": "user", "content": message.content}
    return {"role": "assistant", "content": message.content}


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, api_key: str | None = None, timeout_s: float = 60.0) -> None:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ProviderNotConfiguredError(
                "OpenAI support requires the 'openai' extra: uv sync --extra openai"
            ) from exc
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderNotConfiguredError("OPENAI_API_KEY is not set")
        self._openai = openai
        # SDK-level retries are disabled: the extractor owns retry policy and accounting.
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout_s, max_retries=0)

    @staticmethod
    def build_params(request: CompletionRequest) -> CompletionCreateParamsNonStreaming:
        """The Chat Completions arguments for ``request``, shaped by the model's profile."""
        model = openai_model(request.model)
        kwargs: CompletionCreateParamsNonStreaming = {
            "model": request.model,
            "messages": [_message_param(m) for m in request.messages],
            # Covers reasoning tokens too; max_tokens is deprecated and rejected by them.
            "max_completion_tokens": max(request.max_output_tokens, model.min_output_tokens),
        }
        if model.reasoning_effort is not None:
            kwargs["reasoning_effort"] = model.reasoning_effort
        if model.sampling and request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.json_mode:
            if model.structured_outputs and request.response_schema is not None:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": OUTPUT_SCHEMA_NAME,
                        "schema": dict(request.response_schema),
                        "strict": True,
                    },
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        openai = self._openai
        kwargs = self.build_params(request)
        try:
            response = self._client.chat.completions.create(**kwargs)
        except (
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ) as exc:
            raise ProviderError(f"openai transient error: {exc}", retryable=True) from exc
        except openai.APIError as exc:
            raise ProviderError(f"openai error: {exc}", retryable=False) from exc

        message = response.choices[0].message
        if getattr(message, "refusal", None):
            # A refusal does not follow the schema; repeating the request will not help.
            raise ProviderError(f"openai refusal: {message.refusal}", retryable=False)
        usage = response.usage
        return CompletionResponse(
            text=message.content or "",
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            # completion_tokens already includes reasoning tokens (billed as output).
            output_tokens=usage.completion_tokens if usage else 0,
        )
