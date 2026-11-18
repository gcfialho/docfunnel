"""Local models served by Ollama, through its OpenAI-compatible endpoint."""

from __future__ import annotations

import os

from docfunnel.providers.base import CompletionRequest, CompletionResponse, ProviderError
from docfunnel.providers.capabilities import OpenAIModel, ollama_model
from docfunnel.providers.openai_provider import OpenAIProvider

DEFAULT_HOST = "http://localhost:11434"


def _base_url(host: str) -> str:
    host = host.rstrip("/")
    if "://" not in host:
        host = f"http://{host}"
    return f"{host}/v1"


class OllamaProvider(OpenAIProvider):
    """Runs extraction on a model pulled into a local (or ``OLLAMA_HOST``) Ollama server.

    Local generation is slower than an API, so the default timeout is long. Ollama takes
    images but not PDF files: use the docfunnel or hybrid route.
    """

    name = "ollama"

    def __init__(self, *, host: str | None = None, timeout_s: float = 900.0) -> None:
        host = host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST
        # Ollama ignores the key, but the OpenAI client requires one.
        super().__init__(api_key="ollama", timeout_s=timeout_s, base_url=_base_url(host))

    @staticmethod
    def profile(model: str) -> OpenAIModel:
        return ollama_model(model)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if any(a.media_type == "application/pdf" for a in request.attachments):
            raise ProviderError(
                "ollama models take page images, not PDF files; use the docfunnel or hybrid route",
                retryable=False,
            )
        return super().complete(request)
