"""Candidate generation for Lotto Doctor (Balanced Ensemble be-v1.0.0)."""

from __future__ import annotations

import random
from typing import Any

import numpy as np

from .analyzer import compute_number_features, compute_pair_frequency
from .filters import passes_all_filters
from .models import Draw, NumberFeatures

# 구매자 편향 가중치 (생일 편향 반영 - anti_crowding 전략용)
# 1-31은 생일 선택으로 인해 더 많이 선택됨 → anti_crowding은 이를 회피
_POPULARITY_BIAS: dict[int, float] = {n: (1.5 if n <= 31 else 1.0) for n in range(1, 46)}
_POPULARITY_BIAS.update({7: 2.0, 14: 2.0, 21: 2.0, 28: 2.0,  # 7의 배수 인기
                          1: 1.8, 3: 1.7, 6: 1.7, 13: 0.7})   # 1,3,6 인기 / 13 비인기


def _build_number_pool(
    strategy: str,
    number_features: dict[int, NumberFeatures],
    rng: random.Random,
    top_k: int = 30,
) -> list[int]:
    """가중 비복원 추출로 후보 번호 풀 생성."""
    all_nums = list(range(1, 46))

    if strategy == "recent":
        weights = np.array([number_features[n].recent_20_frequency + 0.01 for n in all_nums])
    elif strategy == "gap":
        weights = np.array([number_features[n].gap_score + 0.01 for n in all_nums])
    elif strategy == "anti_crowding":
        # 실제 anti-crowding: 구매자 편향(생일 번호 등) 역수로 덜 인기있는 번호 선호
        weights = np.array([1.0 / _POPULARITY_BIAS.get(n, 1.0) for n in all_nums])
    else:
        # balanced / random_quality
        weights = np.array([number_features[n].long_frequency + 0.01 for n in all_nums])

    # 정규화
    weights = weights / weights.sum()

    # 가중 비복원 추출 (rng 시드 기반 numpy rng)
    np_rng = np.random.default_rng(rng.randint(0, 2**32 - 1))
    k = min(top_k, 45)
    selected = np_rng.choice(all_nums, size=k, replace=False, p=weights).tolist()
    return selected


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
