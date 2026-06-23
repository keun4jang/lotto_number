"""Utility functions for Lotto Doctor."""

from __future__ import annotations

from datetime import date
from typing import Any


def compute_cumulative_stats(all_results: list[Any]) -> dict[str, int]:
    """Compute cumulative prize stats from all evaluation results."""
    stats: dict[str, int] = {
        "1등": 0, "2등": 0, "3등": 0, "4등": 0, "5등": 0, "낙첨": 0,
    }
    rank_map = {
        "1st": "1등", "2nd": "2등", "3rd": "3등",
        "4th": "4등", "5th": "5등", "no_prize": "낙첨",
    }
    for r in all_results:
        key = rank_map.get(r.rank_label, "낙첨")
        stats[key] = stats.get(key, 0) + 1
    return stats


def format_numbers(numbers: list[int]) -> str:
    """Format a list of lotto numbers for display."""
    return " - ".join(f"{n:02d}" for n in sorted(numbers))


def current_draw_estimate() -> int:
    """Rough estimate of the current draw number based on date."""
    # Draw 1 was on 2002-12-07
    origin = date(2002, 12, 7)
    today = date.today()
    weeks = (today - origin).days // 7
    return max(1, weeks)
