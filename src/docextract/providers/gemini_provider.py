"""Google Gemini backend (google-genai SDK, JSON response MIME type)."""

from __future__ import annotations

import os

from docextract.providers.base import (
    CompletionRequest,
    CompletionResponse,
    ProviderError,
    ProviderNotConfiguredError,
)


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

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        types = self._types
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in request.conversation
        ]
        config = types.GenerateContentConfig(
            system_instruction=request.system or None,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            response_mime_type="application/json" if request.json_mode else None,
        )
        try:
            response = self._client.models.generate_content(
                model=request.model, contents=contents, config=config
            )
        except self._errors.APIError as exc:
            code = getattr(exc, "code", None) or 0
            retryable = code == 429 or code >= 500
            raise ProviderError(f"gemini error: {exc}", retryable=retryable) from exc

        usage = response.usage_metadata
        return CompletionResponse(
            text=response.text or "",
            model=request.model,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        )
