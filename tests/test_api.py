from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docfunnel.api import app
from docfunnel.config import Settings, build_extractor
from docfunnel.service import get_extractor, get_settings

from helpers import US_RECEIPT


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(provider="fake", model="fake-pro", input_dir=tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    extractor = build_extractor(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_extractor] = lambda: extractor
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert (body["provider"], body["model"]) == ("fake", "fake-pro")


def test_extract_text(client: TestClient) -> None:
    response = client.post("/extract", json={"text": US_RECEIPT})
    assert response.status_code == 200
    body = response.json()
    assert body["schema_valid"] is True
    assert body["document"]["total"] == 29.42
    assert body["document"]["date"] == "2023-08-26"
    assert body["needs_review"] is False
    assert body["usage"]["calls"] == 1
    assert body["calls"][0]["model"] == "fake-pro"


def test_extract_flags_inconsistent_document(client: TestClient) -> None:
    misprinted = US_RECEIPT.replace(
        "TOTAL                             $29.42", "TOTAL                             $39.42"
    )
    body = client.post("/extract", json={"text": misprinted}).json()
    assert body["needs_review"] is True
    assert any(r.startswith("total_mismatch") for r in body["review_reasons"])


def test_extract_from_allowed_path(client: TestClient, settings: Settings) -> None:
    (settings.input_dir / "receipt.txt").write_text(US_RECEIPT)
    response = client.post("/extract", json={"path": "receipt.txt"})
    assert response.status_code == 200
    assert response.json()["document"]["vendor_name"] == "Maple Street Hardware"


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({}, 422),
        ({"text": US_RECEIPT, "path": "x.txt"}, 422),
        ({"text": "   "}, 422),
        ({"path": "../etc/passwd"}, 403),
        ({"path": "missing.txt"}, 404),
    ],
)
def test_extract_rejects_bad_requests(client: TestClient, payload: dict, status: int) -> None:
    assert client.post("/extract", json=payload).status_code == status


def test_unsupported_file_type(client: TestClient, settings: Settings) -> None:
    (settings.input_dir / "receipt.docx").write_bytes(b"PK")
    assert client.post("/extract", json={"path": "receipt.docx"}).status_code == 415


def test_path_input_disabled_by_default(settings: Settings) -> None:
    disabled = Settings(provider="fake", model="fake-pro")
    app.dependency_overrides[get_settings] = lambda: disabled
    app.dependency_overrides[get_extractor] = lambda: build_extractor(disabled)
    try:
        with TestClient(app) as client:
            assert client.post("/extract", json={"path": "a.txt"}).status_code == 403
    finally:
        app.dependency_overrides.clear()
