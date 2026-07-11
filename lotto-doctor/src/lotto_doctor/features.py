"""Feature computation for candidate combinations."""

from __future__ import annotations

from typing import Any

from .models import CombinationScore, NumberFeatures
from .popularity import unpopularity_score as _unpopularity_score


def compute_combination_score(
    combo: tuple[int, ...],
    strategy: str,
    number_features: dict[int, NumberFeatures],
    pair_freq: dict[tuple[int, int], int],
    total_draws: int,
    cfg: dict[str, Any],
) -> CombinationScore:
    """Compute all score components for a 6-number combination under a given strategy."""
    weights: dict[str, float] = cfg["scoring"]["weights"].get(
        strategy, cfg["scoring"]["weights"]["balanced"]
    )

    nums = sorted(combo)

    # 1. Long frequency: average normalised frequency of numbers
    long_freq = sum(number_features[n].long_frequency for n in nums) / 6

    # 2. Recent frequency: average of recent_20 frequencies
    recent_freq = sum(number_features[n].recent_20_frequency for n in nums) / 6

    # 3. Gap score: average gap scores (higher = numbers due to appear)
    gap_sc = sum(number_features[n].gap_score for n in nums) / 6

    # 4. Pair score: average pair co-occurrence frequency normalised
    pair_sc = _pair_score(nums, pair_freq, total_draws)

    # 5. Distribution score: how evenly distributed across 1-45
    dist_sc = _distribution_score(nums)

    # 6. Anti-crowding: 구매자 편향 회피 (EV 향상 목적)
    ac_sc = _anti_popularity_score(nums)

    # 7. Diversity: entropy-like measure over tens groups
    div_sc = _diversity_score(nums)

    # 8. Trend: 최근 상승 추세 번호 선호
    trend_sc = sum(number_features[n].trend for n in nums) / 6
    trend_sc = (trend_sc + 1.0) / 2.0  # [-1,1] → [0,1]

    # 9. Stability: 꼽꿨히 나오는 번호
    stability_sc = sum(number_features[n].stability for n in nums) / 6

    # 10. EV score: unpopularity_score (popularity.py 기반)
    ev_sc = _unpopularity_score(nums)

    total = (
        weights.get("long_frequency", 0.0) * long_freq
        + weights.get("recent_frequency", 0.0) * recent_freq
        + weights.get("gap_score", 0.0) * gap_sc
        + weights.get("pair_score", 0.0) * pair_sc
        + weights.get("distribution_score", 0.0) * dist_sc
        + weights.get("anti_crowding", 0.0) * ac_sc
        + weights.get("diversity", 0.0) * div_sc
        + weights.get("trend", 0.0) * trend_sc
        + weights.get("stability", 0.0) * stability_sc
        + weights.get("ev_score", 0.0) * ev_sc
    )

    return CombinationScore(
        numbers=tuple(nums),
        strategy=strategy,
        long_frequency=long_freq,
        recent_frequency=recent_freq,
        gap_score=gap_sc,
        pair_score=pair_sc,
        distribution_score=dist_sc,
        anti_crowding=ac_sc,
        diversity=div_sc,
        total_score=total,
    )


def _pair_score(
    nums: list[int],
    pair_freq: dict[tuple[int, int], int],
    total_draws: int,
) -> float:
    """χ² 기반 pair 점수: 기댓값에 가까운 쌍일수록 높은 점수 (오버피팅 방지)."""
    if total_draws == 0:
        return 0.5
    # 이론적 기댓값: 회차당 C(6,2)=15쌍 / C(45,2)=990쌍
    expected = total_draws * 15 / 990
    scores = []
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            key = (nums[i], nums[j])
            observed = pair_freq.get(key, 0)
            # χ² 기여값 (편차가 클수록 낙은 점수)
            chi2 = (observed - expected) ** 2 / (expected + 1e-9)
            # 정규화: chi2가 낙을수록(기댓값에 가까울수록) 높은 점수
            scores.append(1.0 / (1.0 + chi2 / 10.0))
    return sum(scores) / len(scores) if scores else 0.5


def _distribution_score(nums: list[int]) -> float:
    """How evenly numbers are spread across 1-45 (higher = more uniform)."""
    # Use standard deviation of gaps between consecutive numbers
    extended = [0] + list(nums) + [46]
    gaps = [extended[i + 1] - extended[i] for i in range(len(extended) - 1)]
    mean_gap = 46 / 7  # ~6.57
    import math
    std = math.sqrt(sum((g - mean_gap) ** 2 for g in gaps) / len(gaps))
    max_std = mean_gap  # rough max
    return max(0.0, 1.0 - std / max_std)


def _anti_popularity_score(nums: list[int]) -> float:
    """구매자 편향(생일 번호 등) 역수 점수 - 덜 인기 있는 조합일수록 높은 점수.

    당첨 시 상금 분할을 줄이기 위해 인기 없는 번호 조합을 선호.
    이는 로또에서 수학적으로 기댓값(EV)을 향상시킬 수 있는 유일한 방법.
    """
    _POPULARITY: dict[int, float] = {n: (1.5 if n <= 31 else 1.0) for n in range(1, 46)}
    _POPULARITY.update({7: 2.0, 14: 2.0, 21: 2.0, 28: 2.0, 1: 1.8, 3: 1.7, 6: 1.7, 13: 0.7})
    avg_popularity = sum(_POPULARITY.get(n, 1.0) for n in nums) / 6
    # 평균 인기도 역수를 [0,1]로 정규화 (최소 인기도=0.7, 최대=2.0 기준)
    return max(0.0, min(1.0, (2.0 - avg_popularity) / (2.0 - 0.7)))


def _diversity_score(nums: list[int]) -> float:
    """Entropy-like score based on spread across tens groups (1-9, 10-19, ...)."""
    from collections import Counter
    import math
    groups = Counter((n - 1) // 10 for n in nums)  # 0-4
    total = 6
    entropy = -sum((c / total) * math.log(c / total) for c in groups.values())
    max_entropy = math.log(min(5, 6))  # at most 5 groups
    return entropy / max_entropy if max_entropy > 0 else 0.0
