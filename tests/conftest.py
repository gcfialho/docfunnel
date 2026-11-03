from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from docextract.extractor import Extractor, ModelTarget, RetryPolicy
from docextract.pricing import PriceTable

from helpers import VALID_PAYLOAD, ScriptedProvider


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
def make_extractor(prices: PriceTable) -> Callable[..., tuple[Extractor, list[float]]]:
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
