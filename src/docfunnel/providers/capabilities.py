"""Per-model request capabilities for the real-provider adapters.

Which parameters a model accepts is a property of the model, not something to guess
from its name, so each adapter looks its model up here. Models missing from a table
get that provider's ``DEFAULT``: the request shape that works across that provider's
current models (no sampling parameters, no reasoning controls, JSON mode instead of a
schema where schema support is not documented).

Every entry was checked against the provider's documentation on 2026-11-03; the
README lists the sources. None of them has been exercised against the live APIs yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OpenAIEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
AnthropicEffort = Literal["low", "medium", "high", "xhigh", "max"]
GeminiThinkingLevel = Literal["minimal", "low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class OpenAIModel:
    """Chat Completions parameters for one OpenAI model."""

    structured_outputs: bool = False
    """Send ``response_format: json_schema`` (strict) instead of ``json_object``."""
    sampling: bool = False
    """Accepts ``temperature``. GPT-6 models reject it unless reasoning effort is ``none``."""
    reasoning_effort: OpenAIEffort | None = None
    """``reasoning_effort`` to send; ``None`` leaves the parameter out."""
    min_output_tokens: int = 0
    """Floor for ``max_completion_tokens``, which also covers reasoning tokens."""


@dataclass(frozen=True, slots=True)
class AnthropicModel:
    """Messages API parameters for one Claude model.

    Sampling parameters are never sent: the API version the installed SDK sends
    (``2026-10-21``) rejects ``temperature``/``top_p``/``top_k`` on every model.
    """

    structured_outputs: bool = True
    """Send ``output_config.format`` (available on every model per the docs)."""
    effort: AnthropicEffort | None = None
    """``output_config.effort``; ``None`` leaves it out (it errors on Haiku 4.5)."""
    min_output_tokens: int = 0
    """Floor for ``max_tokens``, which also covers thinking tokens."""


@dataclass(frozen=True, slots=True)
class GeminiModel:
    """``generate_content`` parameters for one Gemini model."""

    structured_outputs: bool = False
    """Send ``response_json_schema`` (otherwise only the JSON MIME type)."""
    sampling: bool = False
    """Accepts ``temperature``. Gemini 3.x docs say to remove sampling parameters."""
    thinking_level: GeminiThinkingLevel | None = None
    """``thinking_config.thinking_level``; ``None`` leaves thinking at the model default."""
    min_output_tokens: int = 0
    """Floor for ``max_output_tokens``, which also covers thought tokens."""


OPENAI_DEFAULT = OpenAIModel()
OPENAI_MODELS: dict[str, OpenAIModel] = {
    # Structured Outputs with json_schema: gpt-4o-mini and later snapshots.
    "gpt-4o-mini": OpenAIModel(structured_outputs=True, sampling=True),
    "gpt-4.1-mini": OpenAIModel(structured_outputs=True, sampling=True),
    # GPT-6: Chat Completions supported, reasoning effort none|low|medium(default)|high|
    # xhigh|max, structured outputs supported, 128K max output. temperature/top_p only
    # with effort "none", so it is not sent at all. Extraction runs at effort "none"
    # on the low-cost tier (no reasoning tokens) and "low" on the step-up model.
    "gpt-6-luna": OpenAIModel(
        structured_outputs=True, reasoning_effort="none", min_output_tokens=4096
    ),
    "gpt-6.1-terra": OpenAIModel(
        structured_outputs=True, reasoning_effort="low", min_output_tokens=16_000
    ),
}

ANTHROPIC_DEFAULT = AnthropicModel()
ANTHROPIC_MODELS: dict[str, AnthropicModel] = {
    # Haiku 4.5: no effort parameter (it errors), thinking off unless requested.
    "claude-haiku-4-5": AnthropicModel(),
    # Haiku 5.5: adaptive thinking is on by default (effort "medium"), billed as output
    # and counted against max_tokens. The migration guide says to leave thinking unset
    # and lower effort: at "low" the model minimizes thinking and skips it on simple
    # tasks. The new tokenizer also uses ~30% more tokens for the same text.
    "claude-haiku-5-5": AnthropicModel(effort="low", min_output_tokens=8192),
    # Sonnet 5.5: "disabled" returns 400; keep adaptive thinking, lower the effort.
    "claude-sonnet-5-5": AnthropicModel(effort="low", min_output_tokens=8192),
    # Opus 5.5 and Fable 5.1: thinking cannot be disabled; effort is the only control.
    "claude-opus-5-5": AnthropicModel(effort="low", min_output_tokens=8192),
    "claude-fable-5-1": AnthropicModel(effort="low", min_output_tokens=8192),
}

GEMINI_DEFAULT = GeminiModel()
GEMINI_MODELS: dict[str, GeminiModel] = {
    # Gemini 2.5 Flash-Lite: thinking off by default; keeps the original request shape.
    "gemini-2.5-flash-lite": GeminiModel(sampling=True),
    # Gemini 3.5 Flash-Lite: thinking on, default level "minimal" (the level the docs
    # recommend for high-volume extraction); thought tokens count against
    # max_output_tokens and are billed. Sampling parameters are to be removed.
    "gemini-3.5-flash-lite": GeminiModel(
        structured_outputs=True, thinking_level="minimal", min_output_tokens=8192
    ),
}


def openai_model(name: str) -> OpenAIModel:
    return OPENAI_MODELS.get(name, OPENAI_DEFAULT)


def anthropic_model(name: str) -> AnthropicModel:
    return ANTHROPIC_MODELS.get(name, ANTHROPIC_DEFAULT)


def gemini_model(name: str) -> GeminiModel:
    return GEMINI_MODELS.get(name, GEMINI_DEFAULT)
