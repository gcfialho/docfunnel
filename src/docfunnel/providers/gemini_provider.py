"""Google Gemini backend (google-genai SDK; JSON Schema output and thinking level per model)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from docfunnel.providers.base import (
    CompletionRequest,
    CompletionResponse,
    ProviderError,
    ProviderNotConfiguredError,
)
from docfunnel.providers.capabilities import gemini_model

if TYPE_CHECKING:
    from google.genai import types as genai_types


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str | None = None) -> None:
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ProviderNotConfiguredError(
                "Gemini support requires the 'gemini' extra: uv sync --extra gemini"
            ) from exc
        api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ProviderNotConfiguredError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set")
        self._types = types
        self._errors = errors
        self._client = genai.Client(api_key=api_key)

    @staticmethod
    def build_config(request: CompletionRequest) -> genai_types.GenerateContentConfig:
        """The ``generate_content`` config for ``request``, shaped by the model's profile."""
        from google.genai import types

        model = gemini_model(request.model)
        config = types.GenerateContentConfig(
            system_instruction=request.system or None,
            # Thought tokens are counted against this limit.
            max_output_tokens=max(request.max_output_tokens, model.min_output_tokens),
        )
        if model.sampling and request.temperature is not None:
            config.temperature = request.temperature
        if model.thinking_level is not None:
            config.thinking_config = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(model.thinking_level.upper())
            )
        if request.json_mode:
            config.response_mime_type = "application/json"
            if model.structured_outputs and request.response_schema is not None:
                config.response_json_schema = dict(request.response_schema)
        return config

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        types = self._types
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in request.conversation
        ]
        try:
            response = self._client.models.generate_content(
                model=request.model, contents=contents, config=self.build_config(request)
            )
        except self._errors.APIError as exc:
            code = getattr(exc, "code", None) or 0
            retryable = code == 429 or code >= 500
            raise ProviderError(f"gemini error: {exc}", retryable=retryable) from exc

        usage = response.usage_metadata
        candidates = (usage.candidates_token_count or 0) if usage else 0
        # Thinking is billed as output, but reported apart from the answer tokens.
        thoughts = (usage.thoughts_token_count or 0) if usage else 0
        return CompletionResponse(
            text=response.text or "",
            model=request.model,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=candidates + thoughts,
        )
