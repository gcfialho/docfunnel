"""Provider-agnostic LLM interface.

Every backend (OpenAI, Anthropic, Gemini, the offline fake, the replay cassette)
implements the same tiny contract: messages in, text + token counts out. Retries,
repair, fallback and accounting live in :mod:`docfunnel.extractor`, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    model: str
    messages: tuple[Message, ...]
    max_output_tokens: int = 2048
    temperature: float | None = 0.0
    json_mode: bool = True

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
