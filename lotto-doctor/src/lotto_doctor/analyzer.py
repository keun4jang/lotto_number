"""Frequency and gap analysis of lotto draw history."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np

from .models import Draw, NumberFeatures


def compute_frequency(draws: list[Draw]) -> dict[int, int]:
    """Count how many times each number 1-45 has appeared."""
    counter: Counter[int] = Counter()
    for draw in draws:
        for n in draw.numbers:
            counter[n] += 1
    return {n: counter.get(n, 0) for n in range(1, 46)}


def compute_recent_frequency(draws: list[Draw], window: int) -> dict[int, int]:
    """Count frequency in the most recent `window` draws."""
    recent = draws[-window:] if len(draws) >= window else draws
    return compute_frequency(recent)


def compute_gap(draws: list[Draw]) -> dict[int, int]:
    """Return draws since last appearance for each number (0 = appeared in last draw)."""
    last_seen: dict[int, int] = {}
    total = len(draws)
    for i, draw in enumerate(draws):
        for n in draw.numbers:
            last_seen[n] = i
    gaps = {}
    for n in range(1, 46):
        if n in last_seen:
            gaps[n] = (total - 1) - last_seen[n]
        else:
            gaps[n] = total  # never appeared
    return gaps


def compute_pair_frequency(draws: list[Draw]) -> dict[tuple[int, int], int]:
    """Count how often each pair of numbers appears together."""
    pair_count: Counter[tuple[int, int]] = Counter()
    for draw in draws:
        nums = sorted(draw.numbers)
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                pair_count[(nums[i], nums[j])] += 1
    return dict(pair_count)


def compute_number_features(
    draws: list[Draw],
    cfg: dict[str, Any],
) -> dict[int, NumberFeatures]:
    """Compute all features for numbers 1-45 given draw history."""
    if not draws:
        # Return neutral features
        return {
            n: NumberFeatures(
                number=n,
                long_frequency=1 / 45,
                recent_20_frequency=1 / 45,
                recent_50_frequency=1 / 45,
                recent_100_frequency=1 / 45,
                gap_score=0.5,
                trend=0.0,
                stability=1.0,
            )
            for n in range(1, 46)
        }

    total = len(draws)
    windows: list[int] = cfg.get("features", {}).get("recent_windows", [20, 50, 100])
    gap_max: int = cfg.get("features", {}).get("gap_max_normalize", 50)

    freq_long = compute_frequency(draws)
    freq_recent: dict[int, dict[int, int]] = {
        w: compute_recent_frequency(draws, w) for w in windows
    }
    gaps = compute_gap(draws)

    # Normalise long frequency
    total_appearances = sum(freq_long.values())
    features: dict[int, NumberFeatures] = {}

    for n in range(1, 46):
        lf = freq_long[n] / total_appearances if total_appearances else 1 / 45
        rf_dict = {
            w: (freq_recent[w][n] / (w * 6 / 45)) for w in windows
        }

        # Gap score: higher score when number hasn't appeared recently (due soon)
        gap = gaps[n]
        gap_score = min(gap / gap_max, 1.0)

        # Trend: compare recent_20 vs recent_50 relative frequency
        trend = 0.0
        if len(windows) >= 2:
            r20 = rf_dict[windows[0]]
            r50 = rf_dict[windows[1]]
            trend = r20 - r50

        # Stability: inverse of variance across recent windows
        window_freqs = [rf_dict[w] for w in windows]
        stability = 1.0 - float(np.std(window_freqs)) if len(window_freqs) > 1 else 1.0
        stability = max(0.0, min(1.0, stability))

        features[n] = NumberFeatures(
            number=n,
            long_frequency=lf,
            recent_20_frequency=rf_dict[windows[0]],
            recent_50_frequency=rf_dict[windows[1]] if len(windows) > 1 else rf_dict[windows[0]],
            recent_100_frequency=rf_dict[windows[2]] if len(windows) > 2 else rf_dict[windows[0]],
            gap_score=gap_score,
            trend=trend,
            stability=stability,
        )

    return features


def get_summary_stats(draws: list[Draw]) -> dict[str, Any]:
    """Return summary statistics for display."""
    if not draws:
        return {}
    freq = compute_frequency(draws)
    gaps = compute_gap(draws)
    sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    sorted_gap = sorted(gaps.items(), key=lambda x: x[1], reverse=True)
    return {
        "total_draws": len(draws),
        "latest_draw_no": draws[-1].draw_no,
        "most_frequent": sorted_freq[:10],
        "least_frequent": sorted_freq[-10:],
        "longest_gap": sorted_gap[:10],
    }
