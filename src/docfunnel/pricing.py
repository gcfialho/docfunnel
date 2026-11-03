"""Token price table and per-call cost computation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float


class PriceTable:
    """Maps model names to USD prices per million tokens.

    Lookups fall back to the longest matching prefix so that dated snapshots
    (``gpt-4o-mini-2024-07-18``) resolve to their family entry. Unknown models cost
    ``None`` - reported as "unknown", never silently as $0.
    """

    def __init__(self, prices: dict[str, ModelPrice]) -> None:
        self._prices = prices

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Mapping[str, float]]) -> PriceTable:
        """Build from ``{model: {"input": usd, "output": usd}}``; skips ``_``-prefixed keys."""
        return cls(
            {
                model: ModelPrice(float(entry["input"]), float(entry["output"]))
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

    def price_for(self, model: str) -> ModelPrice | None:
        if model in self._prices:
            return self._prices[model]
        candidates = [name for name in self._prices if model.startswith(name)]
        return self._prices[max(candidates, key=len)] if candidates else None

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        price = self.price_for(model)
        if price is None:
            return None
        return (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1e6
