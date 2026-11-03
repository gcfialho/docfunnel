"""Record/replay ("cassette") providers.

``RecordingProvider`` wraps a real provider and stores every response keyed by a
hash of the exact request. ``ReplayProvider`` serves those responses back offline,
so a run against a real model can be re-evaluated (or used as a test fixture)
without network access or cost. A request that is not in the cassette fails loudly
instead of silently calling a model.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict
from pathlib import Path

from docextract.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    ProviderError,
)


def request_key(request: CompletionRequest) -> str:
    payload = {
        "model": request.model,
        "messages": [[m.role, m.content] for m in request.messages],
        "json_mode": request.json_mode,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load_cassette(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class ReplayProvider:
    name = "replay"

    def __init__(self, cassette: Path | dict[str, dict]) -> None:
        self._entries = load_cassette(cassette) if isinstance(cassette, Path) else cassette

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        entry = self._entries.get(request_key(request))
        if entry is None:
            raise ProviderError(
                f"request for model {request.model!r} not found in cassette", retryable=False
            )
        return CompletionResponse(**entry)


class RecordingProvider:
    def __init__(self, inner: LLMProvider, cassette: Path) -> None:
        self._inner = inner
        self._path = cassette
        self._entries = load_cassette(cassette)
        self._lock = threading.Lock()  # evals may run documents concurrently
        self.name = inner.name

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        response = self._inner.complete(request)
        with self._lock:
            self._entries[request_key(request)] = asdict(response)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._entries, indent=1, ensure_ascii=False), encoding="utf-8"
            )
        return response
