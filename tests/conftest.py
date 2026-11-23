from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from docfunnel.extract.extractor import Extractor, ModelTarget, RetryPolicy
from docfunnel.extract.pricing import PriceTable

from helpers import VALID_PAYLOAD, DocServer, MakeExtractor, ScriptedProvider


@pytest.fixture
def valid_json() -> str:
    return json.dumps(VALID_PAYLOAD)


@pytest.fixture
def prices() -> PriceTable:
    return PriceTable.from_mapping(
        {
            "test-model": {"input": 1.0, "output": 2.0},
            "backup-model": {"input": 10.0, "output": 20.0},
        }
    )


@pytest.fixture
def make_extractor(prices: PriceTable) -> MakeExtractor:
    def factory(
        *targets: tuple[ScriptedProvider, str], max_attempts: int = 3, backoff_base_s: float = 0.0
    ) -> tuple[Extractor, list[float]]:
        sleeps: list[float] = []
        extractor = Extractor(
            [ModelTarget(provider, model) for provider, model in targets],
            retry=RetryPolicy(max_attempts=max_attempts, backoff_base_s=backoff_base_s),
            prices=prices,
            sleep=sleeps.append,
        )
        return extractor, sleeps

    return factory


@pytest.fixture
def doc_server() -> Iterator[DocServer]:
    """A local HTTP server; tests add ``(status, headers, body)`` per path to ``routes``."""
    server_routes: dict[str, tuple[int, dict[str, str], bytes]] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, headers, body = server_routes.get(self.path, (404, {}, b"not found"))
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            if "Content-Length" not in headers and "X-Stream" not in headers:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield DocServer(f"http://127.0.0.1:{server.server_address[1]}", server_routes)
    finally:
        server.shutdown()
        server.server_close()
