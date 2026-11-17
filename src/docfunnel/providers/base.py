"""Provider-agnostic LLM interface.

Every backend (OpenAI, Anthropic, Gemini, the offline fake, the replay cassette)
implements the same tiny contract: messages in, text + token counts out. Retries,
repair, fallback and accounting live in :mod:`docfunnel.extract.extractor`, not here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Attachment:
    """A file sent to the model itself (native PDF or image input), not as parsed text."""

    data: bytes
    media_type: str  # "application/pdf", "image/png", "image/jpeg", ...


ATTACHMENT_MARKER = re.compile(r"\[\[attachment:(\d+)\]\]")


def interleave(text: str, count: int) -> list[str | int]:
    """Split ``text`` on attachment markers: strings, and 0-based attachment indexes.

    Attachments without a marker come first, in order; a marker for a missing file
    stays as text.
    """
    parts: list[str | int] = []
    used: set[int] = set()
    position = 0
    for match in ATTACHMENT_MARKER.finditer(text):
        index = int(match.group(1)) - 1
        if not 0 <= index < count:
            continue
        parts.append(text[position : match.start()])
        parts.append(index)
        used.add(index)
        position = match.end()
    parts.append(text[position:])
    leading: list[str | int] = [i for i in range(count) if i not in used]
    return [*leading, *(p for p in parts if p != "")]


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    model: str
    messages: tuple[Message, ...]
    max_output_tokens: int = 2048
    temperature: float | None = 0.0
    json_mode: bool = True
    response_schema: Mapping[str, Any] | None = None
    """JSON Schema for native structured output; adapters use it only where the model's
    capability profile allows (see :mod:`docfunnel.providers.capabilities`)."""
    attachments: tuple[Attachment, ...] = ()
    """Files sent with the first user message. Each ``[[attachment:N]]`` marker (1-based) in
    that message is replaced by file N at that point, so files can sit between pages of
    text; files without a marker go before the text. Supported by the Gemini and
    Anthropic adapters; others raise a non-retryable :class:`ProviderError`."""

    @property
    def system(self) -> str:
        return "\n\n".join(m.content for m in self.messages if m.role == "system")

    @property
    def conversation(self) -> tuple[Message, ...]:
        return tuple(m for m in self.messages if m.role != "system")


@dataclass(frozen=True, slots=True)
class CompletionResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None = None
    """Part of ``output_tokens`` spent thinking, when the provider reports it apart."""


class ProviderError(RuntimeError):
    """A provider call failed. ``retryable`` marks transient failures (429/5xx/timeouts)."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderNotConfiguredError(RuntimeError):
    """The provider SDK is not installed or credentials are missing."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(self, request: CompletionRequest) -> CompletionResponse: ...


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token) for providers that do not report usage."""
    return max(1, round(len(text) / 4))
