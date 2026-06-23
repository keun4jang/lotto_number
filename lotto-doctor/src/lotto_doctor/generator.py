"""Candidate generation for Lotto Doctor (Balanced Ensemble be-v1.0.0)."""

from __future__ import annotations

import random
from itertools import combinations
from typing import Any

from .analyzer import compute_number_features, compute_pair_frequency
from .filters import passes_all_filters
from .models import Draw, NumberFeatures
from .scorer import score_candidates


_STRATEGY_BIASES: dict[str, dict[str, float]] = {
    # For each strategy, bias weights on number selection pool
    "balanced": {},
    "recent": {"recent": 2.0},
    "gap": {"gap": 2.0},
    "anti_crowding": {"anti_crowding": 2.0},
    "random_quality": {},
}


def _build_number_pool(
    strategy: str,
    number_features: dict[int, NumberFeatures],
    rng: random.Random,
    top_k: int = 30,
) -> list[int]:
    """Build a weighted pool of candidate numbers for a strategy."""
    all_nums = list(range(1, 46))

    if strategy == "recent":
        # Prefer numbers with high recent_20 frequency
        weights = [number_features[n].recent_20_frequency + 0.01 for n in all_nums]
    elif strategy == "gap":
        # Prefer numbers with high gap score (overdue)
        weights = [number_features[n].gap_score + 0.01 for n in all_nums]
    elif strategy == "anti_crowding":
        # Prefer numbers with lower frequency (less popular)
        weights = [1.0 - number_features[n].long_frequency + 0.01 for n in all_nums]
    else:
        # balanced / random_quality: use long frequency as base
        weights = [number_features[n].long_frequency + 0.01 for n in all_nums]

    # Select top_k numbers from weighted sample (without replacement)
    selected = rng.choices(all_nums, weights=weights, k=min(top_k, 45))
    # Deduplicate preserving order
    seen: set[int] = set()
    pool: list[int] = []
    for n in selected:
        if n not in seen:
            seen.add(n)
            pool.append(n)
    # Ensure at least 6 distinct numbers
    remaining = [n for n in all_nums if n not in seen]
    rng.shuffle(remaining)
    pool.extend(remaining)
    return pool


def _generate_candidates_for_strategy(
    strategy: str,
    count: int,
    number_features: dict[int, NumberFeatures],
    prev_draw: Draw | None,
    cfg: dict[str, Any],
    rng: random.Random,
) -> list[tuple[int, ...]]:
    """Generate `count` candidate combinations for a given strategy."""
    candidates: list[tuple[int, ...]] = []
    attempts = 0
    max_attempts = count * 20

    while len(candidates) < count and attempts < max_attempts:
        attempts += 1
        pool = _build_number_pool(strategy, number_features, rng, top_k=30)
        if len(pool) < 6:
            continue
        combo = tuple(sorted(rng.sample(pool, 6)))
        if passes_all_filters(combo, prev_draw, cfg):
            candidates.append(combo)

    # If we couldn't get enough via biased pool, fill with truly random
    fill_attempts = 0
    while len(candidates) < count and fill_attempts < count * 5:
        fill_attempts += 1
        combo = tuple(sorted(rng.sample(range(1, 46), 6)))
        if passes_all_filters(combo, prev_draw, cfg):
            candidates.append(combo)

    return candidates[:count]


def generate_candidates(
    draws: list[Draw],
    cfg: dict[str, Any],
    seed: int,
) -> dict[str, list[tuple[int, ...]]]:
    """
    Generate 300,000 candidate combinations split by strategy.
    Returns dict[strategy -> list of combinations].
    """
    rng = random.Random(seed)
    strategy_counts: dict[str, int] = cfg["generator"]["strategy_counts"]
    prev_draw = draws[-1] if draws else None

    number_features = compute_number_features(draws, cfg)

    all_candidates: dict[str, list[tuple[int, ...]]] = {}
    for strategy, count in strategy_counts.items():
        candidates = _generate_candidates_for_strategy(
            strategy=strategy,
            count=count,
            number_features=number_features,
            prev_draw=prev_draw,
            cfg=cfg,
            rng=rng,
        )
        all_candidates[strategy] = candidates

    return all_candidates


def select_top_numbers(
    draws: list[Draw],
    cfg: dict[str, Any],
    seed: int,
    top_k: int = 10,
) -> list[tuple[int, float]]:
    """
    Return the top_k candidate numbers with their aggregate scores.
    Used for the 'candidate numbers TOP 10' section.
    """
    number_features = compute_number_features(draws, cfg)
    weights = cfg["scoring"]["weights"]["balanced"]

    scores: dict[int, float] = {}
    for n in range(1, 46):
        feat = number_features[n]
        score = (
            weights.get("long_frequency", 0.0) * feat.long_frequency
            + weights.get("recent_frequency", 0.0) * feat.recent_20_frequency
            + weights.get("gap_score", 0.0) * feat.gap_score
        )
        scores[n] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]
