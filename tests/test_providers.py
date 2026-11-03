import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from docfunnel.config import Settings, build_extractor, parse_target
from docfunnel.pricing import PriceTable
from docfunnel.prompts import OutputParseError, parse_json_object, system_prompt, user_prompt
from docfunnel.providers import DEFAULT_MODELS, ProviderNotConfiguredError, get_provider
from docfunnel.providers.base import CompletionRequest, Message, ProviderError
from docfunnel.providers.fake import FakeProvider, FaultProfile, heuristic_extract
from docfunnel.providers.replay import (
    CassetteEntry,
    RecordingProvider,
    ReplayProvider,
    request_key,
)
from docfunnel.schema import ReceiptExtraction

from helpers import US_RECEIPT


def request_for(text: str, model: str = "fake-pro") -> CompletionRequest:
    return CompletionRequest(
        model=model,
        messages=(Message("system", system_prompt()), Message("user", user_prompt(text))),
    )


def test_heuristic_extract_reads_a_clean_receipt() -> None:
    doc = ReceiptExtraction.model_validate(heuristic_extract(US_RECEIPT))
    assert doc.vendor_name == "Maple Street Hardware"
    assert doc.document_number == "924402"
    assert str(doc.date) == "2023-08-26"
    assert doc.subtotal is not None
    assert doc.tax is not None
    assert doc.total is not None
    assert (doc.currency, float(doc.subtotal), float(doc.tax), float(doc.total)) == (
        "USD",
        27.24,
        2.18,
        29.42,
    )
    assert doc.payment_method == "cash"
    assert [(i.description, i.quantity) for i in doc.line_items] == [
        ("Iced Tea", Decimal(3)),
        ("Hammer 16oz", Decimal(1)),
    ]
    assert doc.vendor_tax_id is None  # absent, and not invented


def test_heuristic_uses_currency_to_resolve_ambiguous_dates() -> None:
    us = heuristic_extract("SHOP\n03/04/2024\nTOTAL  $5.00")
    br = heuristic_extract("LOJA\n03/04/2024\nTOTAL  R$ 5,00")
    assert us["date"] == "2024-03-04"
    assert br["date"] == "2024-04-03"
    assert us["field_confidence"]["date"] < 0.8


def test_fake_provider_is_deterministic() -> None:
    provider = FakeProvider()
    first = provider.complete(request_for(US_RECEIPT, "fake-mini"))
    second = provider.complete(request_for(US_RECEIPT, "fake-mini"))
    assert first == second
    assert first.input_tokens > 0
    assert first.output_tokens > 0


def test_fake_provider_fault_injection_and_repair() -> None:
    provider = FakeProvider({"always-broken": FaultProfile(malformed_json=1.0, fenced_output=0)})
    broken = provider.complete(request_for(US_RECEIPT, "always-broken"))
    with pytest.raises(OutputParseError):
        parse_json_object(broken.text)
    repair = request_for(US_RECEIPT, "always-broken")
    repair = CompletionRequest(
        model=repair.model,
        messages=(
            *repair.messages,
            Message("assistant", broken.text),
            Message("user", "Your previous answer could not be used.\n..."),
        ),
    )
    fixed = provider.complete(repair)
    ReceiptExtraction.model_validate(parse_json_object(fixed.text))


def test_fake_provider_hallucination_fills_an_absent_field() -> None:
    provider = FakeProvider({"liar": FaultProfile(hallucination=1.0, fenced_output=0)})
    data = json.loads(provider.complete(request_for(US_RECEIPT, "liar")).text)
    assert data["vendor_tax_id"] is not None or data["document_number"] != "924402"


def test_fake_provider_requires_a_document_block() -> None:
    request = CompletionRequest(model="fake-mini", messages=(Message("user", "hi"),))
    with pytest.raises(ProviderError):
        FakeProvider().complete(request)


def test_record_then_replay_offline(tmp_path: Path) -> None:
    cassette = tmp_path / "cassette.json"
    recorder = RecordingProvider(FakeProvider(), cassette)
    recorded = recorder.complete(request_for(US_RECEIPT))

    replayed = ReplayProvider(cassette).complete(request_for(US_RECEIPT))

    assert replayed == recorded
    with pytest.raises(ProviderError, match="not found"):
        ReplayProvider(cassette).complete(request_for("another document"))


def test_replay_of_a_hand_written_cassette(tmp_path: Path) -> None:
    """Cassettes are plain JSON, so real-model quirks can be pinned as fixtures."""
    request = request_for(US_RECEIPT, "gpt-6-luna")
    cassette: dict[str, CassetteEntry] = {
        request_key(request): {
            "text": '```json\n{"vendor_name": "Maple Street Hardware", "total": "29.42"}\n```',
            "model": "gpt-6-luna",
            "input_tokens": 812,
            "output_tokens": 61,
        }
    }
    response = ReplayProvider(cassette).complete(request)
    assert response.input_tokens == 812
    assert parse_json_object(response.text)["total"] == "29.42"


def test_price_table_prefix_lookup_and_bundled_defaults() -> None:
    table = PriceTable.load()
    assert table.cost("fake-mini", 10_000, 10_000) == 0.0
    assert table.price_for("gpt-4o-mini-2024-07-18") == table.price_for("gpt-4o-mini")
    assert table.cost("unknown-model", 1, 1) is None


def test_bundled_prices_cover_every_default_model_and_cite_a_source() -> None:
    table = PriceTable.load()
    for model in DEFAULT_MODELS.values():
        assert table.price_for(model) is not None, model
    for model in table.models:
        price = table.price_for(model)
        assert price is not None
        if model.startswith("fake-"):
            continue
        assert price.source is not None, model
        assert price.source.startswith("https://"), model
        assert price.checked is not None, model
        assert date.fromisoformat(price.checked) <= date.today(), model


def test_long_context_rates_apply_to_the_whole_call_above_the_threshold() -> None:
    table = PriceTable.from_mapping(
        {
            "tiered": {
                "input": 0.10,
                "output": 0.50,
                "long_context": {"above_input_tokens": 100_000, "input": 0.50, "output": 2.50},
            }
        }
    )
    assert table.cost("tiered", 100_000, 1_000) == pytest.approx(0.0105)  # at the threshold
    assert table.cost("tiered", 100_001, 1_000) == pytest.approx(0.0525005)


def test_get_provider_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider("cohere")
    with pytest.raises(ProviderNotConfiguredError):
        get_provider("replay")


@pytest.mark.parametrize(
    ("name", "env"), [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")]
)
def test_real_providers_need_credentials(
    monkeypatch: pytest.MonkeyPatch, name: str, env: str
) -> None:
    pytest.importorskip(name)
    monkeypatch.delenv(env, raising=False)
    with pytest.raises(ProviderNotConfiguredError, match=env):
        get_provider(name)


def test_settings_from_env_and_build_extractor() -> None:
    settings = Settings.from_env(
        {
            "DOCFUNNEL_PROVIDER": "fake",
            "DOCFUNNEL_FALLBACK": "fake:fake-pro",
            "DOCFUNNEL_MAX_ATTEMPTS": "2",
            "DOCFUNNEL_REVIEW_MIN_CONFIDENCE": "0.8",
        }
    )
    assert settings.primary == ("fake", "fake-mini")
    extractor = build_extractor(settings)
    assert [t.label for t in extractor.targets] == ["fake:fake-mini", "fake:fake-pro"]
    assert extractor.retry.max_attempts == 2
    assert extractor.retry.backoff_base_s == 0.0  # no sleeping against offline providers
    assert extractor.review.min_confidence == 0.8


def test_parse_target_defaults_model() -> None:
    assert parse_target("anthropic") == ("anthropic", "claude-haiku-5-5")
    assert parse_target("openai") == ("openai", "gpt-6-luna")
    assert parse_target("gemini") == ("gemini", "gemini-3.5-flash-lite")
    assert parse_target("openai:gpt-6.1-terra") == ("openai", "gpt-6.1-terra")
