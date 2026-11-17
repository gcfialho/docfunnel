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

import dataclasses
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
    # Gemini 3.1 Flash-Lite: JSON Schema output; thinking left at the model default.
    "gemini-3.1-flash-lite": GeminiModel(structured_outputs=True, min_output_tokens=8192),
    # Gemini 3.8 Flash: thinking on by default at "medium"; "minimal" is rejected, so the
    # lowest level is "low".
    "gemini-3.8-flash": GeminiModel(
        structured_outputs=True, thinking_level="low", min_output_tokens=8192
    ),
}


# ---- variants: one model with some parameters changed, for ablations ------------------
#
# ``gemini-3.8-flash+thinking_level=medium`` is gemini-3.8-flash with its table entry's
# thinking level replaced. The API receives the base name, prices are looked up by it
# (prefix match), and reports keep the full name, so two variants of one model can be
# compared in one run. Values: true/false, integers, a literal, or none.

VARIANT_SEPARATOR = "+"


def base_model(name: str) -> str:
    """The model name to send to the API: ``name`` without its variant options."""
    return name.split(VARIANT_SEPARATOR, 1)[0]


def _with_options[P: (OpenAIModel, AnthropicModel, GeminiModel)](profile: P, name: str) -> P:
    options = name.split(VARIANT_SEPARATOR)[1:]
    if not options:
        return profile
    fields = {f.name: f for f in dataclasses.fields(profile)}
    changes: dict[str, object] = {}
    for option in options:
        key, sep, raw = option.partition("=")
        if not sep or key not in fields:
            raise ValueError(
                f"model option {option!r} must be key=value with key in {sorted(fields)}"
            )
        kind = str(fields[key].type)
        if kind == "bool":
            changes[key] = raw.lower() in {"1", "true", "yes", "on"}
        elif kind == "int":
            changes[key] = int(raw)
        else:
            changes[key] = None if raw.lower() in {"none", "null", ""} else raw
    return dataclasses.replace(profile, **changes)  # type: ignore[arg-type]


def openai_model(name: str) -> OpenAIModel:
    return _with_options(OPENAI_MODELS.get(base_model(name), OPENAI_DEFAULT), name)


def anthropic_model(name: str) -> AnthropicModel:
    return _with_options(ANTHROPIC_MODELS.get(base_model(name), ANTHROPIC_DEFAULT), name)


def gemini_model(name: str) -> GeminiModel:
    return _with_options(GEMINI_MODELS.get(base_model(name), GEMINI_DEFAULT), name)
