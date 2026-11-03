"""LLM providers and the factory that selects one by name."""

from __future__ import annotations

from pathlib import Path

from docextract.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    Message,
    ProviderError,
    ProviderNotConfiguredError,
)
from docextract.providers.fake import FakeProvider

PROVIDER_NAMES = ("fake", "openai", "anthropic", "gemini", "replay")

DEFAULT_MODELS: dict[str, str] = {
    "fake": "fake-mini",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "gemini": "gemini-2.5-flash",
}


def get_provider(name: str, *, cassette: Path | None = None) -> LLMProvider:
    """Instantiate a provider by name. Real providers import their SDK lazily."""
    match name:
        case "fake":
            return FakeProvider()
        case "openai":
            from docextract.providers.openai_provider import OpenAIProvider

            return OpenAIProvider()
        case "anthropic":
            from docextract.providers.anthropic_provider import AnthropicProvider

            return AnthropicProvider()
        case "gemini":
            from docextract.providers.gemini_provider import GeminiProvider

            return GeminiProvider()
        case "replay":
            from docextract.providers.replay import ReplayProvider

            if cassette is None:
                raise ProviderNotConfiguredError("the replay provider needs a cassette path")
            return ReplayProvider(cassette)
        case _:
            raise ValueError(f"unknown provider {name!r}; expected one of {PROVIDER_NAMES}")


__all__ = [
    "DEFAULT_MODELS",
    "PROVIDER_NAMES",
    "CompletionRequest",
    "CompletionResponse",
    "FakeProvider",
    "LLMProvider",
    "Message",
    "ProviderError",
    "ProviderNotConfiguredError",
    "get_provider",
]
