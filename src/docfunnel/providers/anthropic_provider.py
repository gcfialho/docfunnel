"""Anthropic Messages API backend."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from docfunnel.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderError,
    ProviderNotConfiguredError,
)

if TYPE_CHECKING:
    from anthropic.types import MessageParam


def _message_param(message: Message) -> MessageParam:
    # One branch per role so each dict matches exactly one of the SDK's message TypedDicts.
    if message.role == "user":
        return {"role": "user", "content": message.content}
    if message.role == "assistant":
        return {"role": "assistant", "content": message.content}
    return {"role": "system", "content": message.content}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, timeout_s: float = 60.0) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ProviderNotConfiguredError(
                "Anthropic support requires the 'anthropic' extra: uv sync --extra anthropic"
            ) from exc
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderNotConfiguredError("ANTHROPIC_API_KEY is not set")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=0)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        anthropic = self._anthropic
        try:
            response = self._client.messages.create(
                model=request.model,
                max_tokens=request.max_output_tokens,
                system=request.system,
                messages=[_message_param(m) for m in request.conversation],
            )
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise ProviderError(f"anthropic connection error: {exc}", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            retryable = exc.status_code == 429 or exc.status_code >= 500
            raise ProviderError(f"anthropic error: {exc}", retryable=retryable) from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        return CompletionResponse(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
