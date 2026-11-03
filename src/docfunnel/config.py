"""Runtime configuration from environment variables.

=====================================  ================================================
``DOCFUNNEL_PROVIDER``                 fake | openai | anthropic | gemini | replay
``DOCFUNNEL_MODEL``                    model name (defaults per provider)
``DOCFUNNEL_FALLBACK``                 comma-separated ``provider:model`` chain
``DOCFUNNEL_MAX_ATTEMPTS``             attempts per model (default 3)
``DOCFUNNEL_BACKOFF_BASE_S``           base backoff in seconds (default 0.5)
``DOCFUNNEL_REVIEW_MIN_CONFIDENCE``    review threshold for field confidence (0.7)
``DOCFUNNEL_PRICING_FILE``             JSON price table overriding the bundled one
``DOCFUNNEL_CASSETTE``                 cassette path for the replay provider
``DOCFUNNEL_INPUT_DIR``                directory the API may read files from (off if unset)
=====================================  ================================================
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from docfunnel.extractor import Extractor, ModelTarget, RetryPolicy
from docfunnel.pricing import PriceTable
from docfunnel.providers import DEFAULT_MODELS, get_provider
from docfunnel.validation import ReviewPolicy


def parse_target(spec: str) -> tuple[str, str]:
    """``"openai:gpt-4o-mini"`` -> ``("openai", "gpt-4o-mini")``; ``"openai"`` -> default model."""
    provider, _, model = spec.strip().partition(":")
    if not provider:
        raise ValueError(f"invalid target spec {spec!r}")
    return provider, model or DEFAULT_MODELS.get(provider, "")


@dataclass(frozen=True)
class Settings:
    provider: str = "fake"
    model: str | None = None
    fallbacks: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    max_attempts: int = 3
    backoff_base_s: float = 0.5
    review_min_confidence: float = 0.7
    pricing_file: Path | None = None
    cassette: Path | None = None
    input_dir: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        def path(name: str) -> Path | None:
            value = env.get(name)
            return Path(value) if value else None

        fallback_spec = env.get("DOCFUNNEL_FALLBACK", "")
        return cls(
            provider=env.get("DOCFUNNEL_PROVIDER", "fake"),
            model=env.get("DOCFUNNEL_MODEL") or None,
            fallbacks=tuple(parse_target(s) for s in fallback_spec.split(",") if s.strip()),
            max_attempts=int(env.get("DOCFUNNEL_MAX_ATTEMPTS", "3")),
            backoff_base_s=float(env.get("DOCFUNNEL_BACKOFF_BASE_S", "0.5")),
            review_min_confidence=float(env.get("DOCFUNNEL_REVIEW_MIN_CONFIDENCE", "0.7")),
            pricing_file=path("DOCFUNNEL_PRICING_FILE"),
            cassette=path("DOCFUNNEL_CASSETTE"),
            input_dir=path("DOCFUNNEL_INPUT_DIR"),
        )

    def with_overrides(self, **overrides: object) -> Settings:
        return replace(self, **{k: v for k, v in overrides.items() if v is not None})

    @property
    def primary(self) -> tuple[str, str]:
        return self.provider, self.model or DEFAULT_MODELS.get(self.provider, "")


def build_extractor(settings: Settings) -> Extractor:
    chain = [settings.primary, *settings.fallbacks]
    targets = [
        ModelTarget(get_provider(provider, cassette=settings.cassette), model)
        for provider, model in chain
    ]
    # Backing off against a local deterministic stub only slows tests down.
    offline = all(provider in {"fake", "replay"} for provider, _ in chain)
    return Extractor(
        targets,
        retry=RetryPolicy(
            max_attempts=settings.max_attempts,
            backoff_base_s=0.0 if offline else settings.backoff_base_s,
        ),
        review=ReviewPolicy(min_confidence=settings.review_min_confidence),
        prices=PriceTable.load(settings.pricing_file),
    )
