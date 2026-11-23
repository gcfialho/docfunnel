"""Regression-gate primitives shared by ``docfunnel compare`` and ``compare-parse``.

A :class:`Check` names a metric, which direction is better and how much it may get
worse. :func:`evaluate_check` turns a baseline/candidate pair into a :class:`Status`,
and a :class:`Comparison` passes when no check regressed and both runs used the same
dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Direction(StrEnum):
    HIGHER_IS_BETTER = "higher"
    LOWER_IS_BETTER = "lower"


@dataclass(frozen=True)
class Check:
    metric: str
    direction: Direction
    tolerance: float | None  # None disables the check
    relative: bool = False  # tolerance as a fraction of the baseline value


class Status(StrEnum):
    PASS = "pass"
    REGRESSION = "REGRESSION"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CheckResult:
    check: Check
    baseline: float | None
    candidate: float | None
    status: Status

    @property
    def delta(self) -> float | None:
        if self.baseline is None or self.candidate is None:
            return None
        return self.candidate - self.baseline


@dataclass(frozen=True)
class Comparison:
    results: list[CheckResult]
    dataset_matches: bool

    @property
    def passed(self) -> bool:
        return self.dataset_matches and all(r.status is not Status.REGRESSION for r in self.results)


def evaluate_check(check: Check, baseline: float | None, candidate: float | None) -> Status:
    if check.tolerance is None or baseline is None or candidate is None:
        return Status.SKIPPED
    allowed = check.tolerance * abs(baseline) if check.relative else check.tolerance
    worse_by = (
        baseline - candidate
        if check.direction is Direction.HIGHER_IS_BETTER
        else candidate - baseline
    )
    return Status.REGRESSION if worse_by > allowed + 1e-12 else Status.PASS
