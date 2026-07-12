"""Pension Lottery 720+ frequency analysis."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .pension_models import PensionDraw


def get_jo_frequency(draws: list[PensionDraw]) -> dict[int, int]:
    """Count how many times each 조(1~5) appeared."""
    return dict(Counter(d.jo for d in draws))


def get_digit_frequency(draws: list[PensionDraw]) -> list[dict[int, int]]:
    """Return per-position digit frequency.

    Returns a list of 6 dicts, each mapping digit(0-9) → count.
    """
    freq: list[Counter] = [Counter() for _ in range(6)]
    for d in draws:
        for pos, digit in enumerate(d.digits):
            freq[pos][digit] += 1
    return [dict(f) for f in freq]


def get_digit_frequency_recent(draws: list[PensionDraw], n: int = 50) -> list[dict[int, int]]:
    """Per-position digit frequency for the last n draws."""
    return get_digit_frequency(draws[-n:])


def get_summary_stats(draws: list[PensionDraw]) -> dict[str, Any]:
    if not draws:
        return {}
    jo_freq = get_jo_frequency(draws)
    digit_freq = get_digit_frequency(draws)
    return {
        "total_draws": len(draws),
        "latest_draw_no": draws[-1].draw_no,
        "jo_frequency": jo_freq,
        "digit_frequency": digit_freq,
    }


def digit_weights(freq: dict[int, int]) -> list[float]:
    """Convert digit frequency dict to probability weights for digits 0-9."""
    total = sum(freq.values()) or 1
    return [freq.get(d, 0) / total for d in range(10)]
