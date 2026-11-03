import json
from decimal import Decimal

import pytest

from docfunnel.extractor import RetryPolicy
from docfunnel.prompts import REPAIR_MARKER, output_schema
from docfunnel.providers.base import ProviderError

from helpers import US_RECEIPT, VALID_PAYLOAD, MakeExtractor, ScriptedProvider


def test_happy_path_tracks_tokens_cost_and_latency(
    make_extractor: MakeExtractor, valid_json: str
) -> None:
    provider = ScriptedProvider([valid_json])
    extractor, sleeps = make_extractor((provider, "test-model"))

    result = extractor.extract(US_RECEIPT)

    assert result.schema_valid
    assert result.first_attempt_schema_valid
    assert result.document is not None
    assert result.document.total == Decimal("29.42")
    assert not result.needs_review
    assert result.attempts == 1
    assert not result.used_fallback
    assert result.usage.input_tokens == 1000
    assert result.usage.output_tokens == 200
    # 1000 * $1/M + 200 * $2/M
    assert result.usage.cost_usd == pytest.approx(0.0014)
    assert result.calls[0].latency_ms >= 0
    assert sleeps == []
    assert provider.requests[0].response_schema == output_schema()


def test_invalid_json_triggers_repair_prompt(
    make_extractor: MakeExtractor, valid_json: str
) -> None:
    provider = ScriptedProvider(['{"vendor_name": "Maple', valid_json])
    extractor, _ = make_extractor((provider, "test-model"))

    result = extractor.extract(US_RECEIPT)

    assert result.schema_valid
    assert not result.first_attempt_schema_valid
    assert [c.status for c in result.calls] == ["invalid_json", "ok"]
    assert [c.purpose for c in result.calls] == ["extract", "repair"]
    repair_request = provider.requests[1]
    assert [m.role for m in repair_request.messages] == ["system", "user", "assistant", "user"]
    assert REPAIR_MARKER in repair_request.messages[-1].content


def test_schema_error_is_reported_back_to_the_model(
    make_extractor: MakeExtractor, valid_json: str
) -> None:
    bad = json.dumps(VALID_PAYLOAD | {"total": "see line items"})
    provider = ScriptedProvider([bad, valid_json])
    extractor, _ = make_extractor((provider, "test-model"))

    result = extractor.extract(US_RECEIPT)

    assert result.schema_valid
    assert result.calls[0].status == "schema_error"
    assert "total" in provider.requests[1].messages[-1].content


def test_backoff_between_retries(make_extractor: MakeExtractor, valid_json: str) -> None:
    provider = ScriptedProvider(["nope", "still nope", valid_json])
    extractor, sleeps = make_extractor((provider, "test-model"), backoff_base_s=1.0)

    assert extractor.extract(US_RECEIPT).schema_valid
    assert len(sleeps) == 2
    assert 0.5 <= sleeps[0] <= 1.0  # equal jitter on 1s
    assert 1.0 <= sleeps[1] <= 2.0  # equal jitter on 2s


def test_backoff_is_capped() -> None:
    import random

    policy = RetryPolicy(backoff_base_s=1.0, backoff_max_s=4.0)
    assert policy.delay(10, random.Random(0)) <= 4.0
    assert RetryPolicy(backoff_base_s=0).delay(3, random.Random(0)) == 0.0


def test_transient_provider_errors_are_retried(
    make_extractor: MakeExtractor, valid_json: str
) -> None:
    provider = ScriptedProvider([ProviderError("429", retryable=True), valid_json])
    extractor, _ = make_extractor((provider, "test-model"))

    result = extractor.extract(US_RECEIPT)

    assert result.schema_valid
    assert [c.status for c in result.calls] == ["provider_error", "ok"]
    # A transport retry resends the same request, not a repair prompt.
    assert provider.requests[0].messages == provider.requests[1].messages


def test_fallback_after_exhausting_primary(make_extractor: MakeExtractor, valid_json: str) -> None:
    primary = ScriptedProvider(["garbage"] * 3, name="primary")
    backup = ScriptedProvider([valid_json], name="backup")
    extractor, _ = make_extractor((primary, "test-model"), (backup, "backup-model"))

    result = extractor.extract(US_RECEIPT)

    assert result.schema_valid
    assert result.used_fallback
    assert (result.provider, result.model) == ("backup", "backup-model")
    assert len(result.calls) == 4
    # Cost is accounted per model: 3 cheap failed calls + 1 expensive one.
    assert result.usage.cost_usd == pytest.approx(3 * 0.0014 + 0.014)


def test_non_retryable_error_skips_to_fallback(
    make_extractor: MakeExtractor, valid_json: str
) -> None:
    primary = ScriptedProvider([ProviderError("401", retryable=False)], name="primary")
    backup = ScriptedProvider([valid_json], name="backup")
    extractor, _ = make_extractor((primary, "test-model"), (backup, "backup-model"))

    result = extractor.extract(US_RECEIPT)

    assert result.used_fallback
    assert len(primary.requests) == 1


def test_total_failure_returns_review_result_instead_of_raising(
    make_extractor: MakeExtractor,
) -> None:
    extractor, _ = make_extractor((ScriptedProvider(["x", "y"]), "test-model"), max_attempts=2)

    result = extractor.extract(US_RECEIPT)

    assert result.document is None
    assert not result.schema_valid
    assert result.needs_review
    assert result.review_reasons == ["extraction_failed"]
    assert result.attempts == 2


def test_business_rule_violation_routes_to_review_without_retry(
    make_extractor: MakeExtractor,
) -> None:
    inconsistent = json.dumps(VALID_PAYLOAD | {"total": 35.00})
    provider = ScriptedProvider([inconsistent])
    extractor, _ = make_extractor((provider, "test-model"))

    result = extractor.extract(US_RECEIPT)

    assert result.attempts == 1
    assert result.needs_review
    assert any(r.startswith("total_mismatch") for r in result.review_reasons)


def test_unknown_model_price_is_reported_as_unknown(
    make_extractor: MakeExtractor, valid_json: str
) -> None:
    extractor, _ = make_extractor((ScriptedProvider([valid_json]), "mystery-model"))
    assert extractor.extract(US_RECEIPT).usage.cost_usd is None


@pytest.mark.parametrize("text", ["", "   ", "x" * 30_001])
def test_rejects_empty_or_oversized_input(make_extractor: MakeExtractor, text: str) -> None:
    extractor, _ = make_extractor((ScriptedProvider([]), "test-model"))
    with pytest.raises(ValueError, match="document"):
        extractor.extract(text)
