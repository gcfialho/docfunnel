"""Token price table and per-call cost computation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LongContextPrice:
    """Higher rates that apply to the whole call once its input exceeds a threshold."""

    above_input_tokens: int
    input_per_mtok: float
    output_per_mtok: float


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float
    long_context: LongContextPrice | None = None
    source: str | None = None
    checked: str | None = None

    def rates(self, input_tokens: int) -> tuple[float, float]:
        """``(input, output)`` USD per 1M tokens for a call with this many input tokens."""
        tier = self.long_context
        if tier is not None and input_tokens > tier.above_input_tokens:
            return tier.input_per_mtok, tier.output_per_mtok
        return self.input_per_mtok, self.output_per_mtok


def _model_price(entry: Mapping[str, Any]) -> ModelPrice:
    long_context = entry.get("long_context")
    return ModelPrice(
        float(entry["input"]),
        float(entry["output"]),
        long_context=(
            None
            if long_context is None
            else LongContextPrice(
                int(long_context["above_input_tokens"]),
                float(long_context["input"]),
                float(long_context["output"]),
            )
        ),
        source=entry.get("source"),
        checked=entry.get("checked"),
    )


class PriceTable:
    """Maps model names to USD prices per million tokens.

    Lookups fall back to the longest matching prefix so that dated snapshots
    (``gpt-4o-mini-2024-07-18``) resolve to their family entry. Unknown models cost
    ``None`` - reported as "unknown", never silently as $0.
    """

    def __init__(self, prices: dict[str, ModelPrice]) -> None:
        self._prices = prices

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Mapping[str, Any]]) -> PriceTable:
        """Build from ``{model: {"input": usd, "output": usd, ...}}``; skips ``_``-prefixed keys.

        Optional per-model keys: ``long_context`` (``{"above_input_tokens": n, "input": usd,
        "output": usd}``), ``source`` (URL of the pricing page) and ``checked`` (ISO date).
        """
        return cls(
            {
                model: _model_price(entry)
                for model, entry in raw.items()
                if not model.startswith("_")
            }
        )

    @classmethod
    def load(cls, path: Path | None = None) -> PriceTable:
        if path is None:
            text = resources.files("docfunnel").joinpath("pricing.json").read_text("utf-8")
        else:
            text = path.read_text(encoding="utf-8")
        return cls.from_mapping(json.loads(text))

    @property
    def models(self) -> list[str]:
        return sorted(self._prices)

    def price_for(self, model: str) -> ModelPrice | None:
        if model in self._prices:
            return self._prices[model]
        candidates = [name for name in self._prices if model.startswith(name)]
        return self._prices[max(candidates, key=len)] if candidates else None

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        price = self.price_for(model)
        if price is None:
            return None
        input_rate, output_rate = price.rates(input_tokens)
        return (input_tokens * input_rate + output_tokens * output_rate) / 1e6
