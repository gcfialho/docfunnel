"""LLM providers and the factory that selects one by name."""

from __future__ import annotations

from pathlib import Path

from docfunnel.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    Message,
    ProviderError,
    ProviderNotConfiguredError,
)
from docfunnel.providers.fake import FakeProvider

PROVIDER_NAMES = ("fake", "openai", "anthropic", "gemini", "replay")

DEFAULT_MODELS: dict[str, str] = {
    "fake": "fake-mini",
    "openai": "gpt-6-luna",
    "anthropic": "claude-haiku-5-5",
    "gemini": "gemini-3.5-flash-lite",
}
"""The cheapest current general model of each provider; prices are in ``pricing.json``."""


def get_provider(name: str, *, cassette: Path | None = None) -> LLMProvider:
    """Instantiate a provider by name. Real providers import their SDK lazily."""
    match name:
        case "fake":
            return FakeProvider()
        case "openai":
            from docfunnel.providers.openai_provider import OpenAIProvider

            return OpenAIProvider()
        case "anthropic":
            from docfunnel.providers.anthropic_provider import AnthropicProvider

            return AnthropicProvider()
        case "gemini":
            from docfunnel.providers.gemini_provider import GeminiProvider

            return GeminiProvider()
        case "replay":
            from docfunnel.providers.replay import ReplayProvider

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
