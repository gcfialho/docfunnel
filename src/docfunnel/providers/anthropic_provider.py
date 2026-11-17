"""Anthropic Messages API backend (structured outputs and thinking controls per model)."""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING, Literal, cast

from docfunnel.providers.base import (
    Attachment,
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderError,
    ProviderNotConfiguredError,
)
from docfunnel.providers.capabilities import anthropic_model, base_model

if TYPE_CHECKING:
    from anthropic.types import (
        ContentBlockParam,
        ImageBlockParam,
        MessageParam,
        OutputConfigParam,
    )
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming


_ImageType = Literal["image/png", "image/jpeg", "image/gif", "image/webp"]
_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


def _message_param(message: Message) -> MessageParam:
    # One branch per role so each dict matches exactly one of the SDK's message TypedDicts.
    if message.role == "user":
        return {"role": "user", "content": message.content}
    if message.role == "assistant":
        return {"role": "assistant", "content": message.content}
    return {"role": "system", "content": message.content}


def _attachment_block(attachment: Attachment) -> ContentBlockParam:
    data = base64.standard_b64encode(attachment.data).decode("ascii")
    if attachment.media_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    if attachment.media_type in _IMAGE_TYPES:
        image: ImageBlockParam = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": cast(_ImageType, attachment.media_type),
                "data": data,
            },
        }
        return image
    raise ProviderError(
        f"anthropic cannot take {attachment.media_type!r} attachments", retryable=False
    )


def _messages(request: CompletionRequest) -> list[MessageParam]:
    messages = [_message_param(m) for m in request.conversation]
    if request.attachments and messages:
        blocks = [_attachment_block(a) for a in request.attachments]
        blocks.append({"type": "text", "text": request.conversation[0].content})
        messages[0] = {"role": "user", "content": blocks}
    return messages


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
            raise ProviderNotConfiguredError(
                "ANTHROPIC_API_KEY is not set; set it, or choose another provider with --provider"
            )
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=0)

    @staticmethod
    def build_params(request: CompletionRequest) -> MessageCreateParamsNonStreaming:
        """The Messages API arguments for ``request``, shaped by the model's profile.

        ``request.temperature`` is ignored: the SDK sends API version 2026-10-21, which
        rejects sampling parameters on every model.
        """
        model = anthropic_model(request.model)
        kwargs: MessageCreateParamsNonStreaming = {
            "model": base_model(request.model),
            # Thinking, where the model runs it, is counted against max_tokens.
            "max_tokens": max(request.max_output_tokens, model.min_output_tokens),
            "system": request.system,
            "messages": _messages(request),
        }
        output_config: OutputConfigParam = {}
        if model.effort is not None:
            output_config["effort"] = model.effort
        if request.json_mode and model.structured_outputs and request.response_schema:
            output_config["format"] = {
                "type": "json_schema",
                "schema": dict(request.response_schema),
            }
        if output_config:
            kwargs["output_config"] = output_config
        # ``thinking`` is never sent: models that think do so adaptively by default, and
        # effort is the documented control (disabling it is rejected on several models).
        return kwargs

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        anthropic = self._anthropic
        try:
            response = self._client.messages.create(**self.build_params(request))
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise ProviderError(f"anthropic connection error: {exc}", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            retryable = exc.status_code == 429 or exc.status_code >= 500
            raise ProviderError(f"anthropic error: {exc}", retryable=retryable) from exc

        if response.stop_reason == "refusal":
            # Safety classifiers declined (HTTP 200); Haiku 5.5 has no server-side fallback.
            raise ProviderError("anthropic refusal (stop_reason=refusal)", retryable=False)
        # Read text blocks by type: thinking blocks can come first.
        text = "".join(block.text for block in response.content if block.type == "text")
        return CompletionResponse(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
