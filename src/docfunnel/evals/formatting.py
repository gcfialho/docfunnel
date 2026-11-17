"""Number formatting shared by the Markdown reports and regression checks."""

from __future__ import annotations


def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def fmt_usd(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.6f}"


def fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f} ms"
