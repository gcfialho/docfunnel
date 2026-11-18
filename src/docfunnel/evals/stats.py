"""Small numeric helpers shared by both evaluations."""

from __future__ import annotations

import math
from collections.abc import Sequence


def safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return 2 * precision * recall / (precision + recall)


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Linear-interpolated percentile (same convention as numpy's default)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion; sound at 0% and 100%, unlike p ± 2·SE."""
    if trials == 0:
        return (0.0, 1.0)
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact_p(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar test on the discordant pairs of a paired comparison.

    ``only_a``: items A got right and B wrong; ``only_b``: the reverse. Items both got
    right or both got wrong say nothing about which is better and are left out.
    """
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail: float = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)
