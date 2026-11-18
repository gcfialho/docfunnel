"""OpenAI Chat Completions backend (Structured Outputs or JSON mode, per model)."""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING

from docfunnel.extract.prompts import OUTPUT_SCHEMA_NAME
from docfunnel.providers.base import (
    Attachment,
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderError,
    ProviderNotConfiguredError,
    interleave,
)
from docfunnel.providers.capabilities import OpenAIModel, base_model, openai_model

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam
    from openai.types.chat.completion_create_params import CompletionCreateParamsNonStreaming


def _message_param(message: Message) -> ChatCompletionMessageParam:
    # One branch per role so each dict matches exactly one of the SDK's message TypedDicts.
    if message.role == "system":
        return {"role": "system", "content": message.content}
    if message.role == "user":
        return {"role": "user", "content": message.content}
    return {"role": "assistant", "content": message.content}


_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


def _attachment_part(attachment: Attachment, index: int) -> ChatCompletionContentPartParam:
    data = base64.standard_b64encode(attachment.data).decode("ascii")
    url = f"data:{attachment.media_type};base64,{data}"
    if attachment.media_type == "application/pdf":
        # The API reads both the text layer and an image of every page.
        return {"type": "file", "file": {"filename": f"document-{index + 1}.pdf", "file_data": url}}
    if attachment.media_type in _IMAGE_TYPES:
        # "high" keeps small print legible; "auto" may downscale a scanned page.
        return {"type": "image_url", "image_url": {"url": url, "detail": "high"}}
    raise ProviderError(
        f"openai cannot take {attachment.media_type!r} files; send a PDF or an image",
        retryable=False,
    )


def _messages(request: CompletionRequest) -> list[ChatCompletionMessageParam]:
    messages = [_message_param(m) for m in request.messages]
    if not request.attachments:
        return messages
    first_user = next((i for i, m in enumerate(request.messages) if m.role == "user"), None)
    if first_user is None:
        raise ProviderError("attachments need a user message to go with", retryable=False)
    content = request.messages[first_user].content
    parts: list[ChatCompletionContentPartParam] = [
        {"type": "text", "text": part}
        if isinstance(part, str)
        else _attachment_part(request.attachments[part], part)
        for part in interleave(content, len(request.attachments))
    ]
    messages[first_user] = {"role": "user", "content": parts}
    return messages


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        base_url: str | None = None,
    ) -> None:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ProviderNotConfiguredError(
                "OpenAI support requires the 'openai' extra: uv sync --extra openai"
            ) from exc
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderNotConfiguredError(
                "OPENAI_API_KEY is not set; set it, or choose another provider with --provider"
            )
        self._openai = openai
        # SDK-level retries are disabled: the extractor owns retry policy and accounting.
        self._client = openai.OpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=0
        )

    @staticmethod
    def profile(model: str) -> OpenAIModel:
        """The request parameters this backend uses for ``model``."""
        return openai_model(model)

    @classmethod
    def build_params(cls, request: CompletionRequest) -> CompletionCreateParamsNonStreaming:
        """The Chat Completions arguments for ``request``, shaped by the model's profile."""
        model = cls.profile(request.model)
        kwargs: CompletionCreateParamsNonStreaming = {
            "model": base_model(request.model),
            "messages": _messages(request),
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
        details = usage.completion_tokens_details if usage else None
        return CompletionResponse(
            text=message.content or "",
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            # completion_tokens already includes reasoning tokens (billed as output).
            output_tokens=usage.completion_tokens if usage else 0,
            reasoning_tokens=details.reasoning_tokens if details else None,
        )
