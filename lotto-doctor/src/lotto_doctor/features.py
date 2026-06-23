"""Feature computation for candidate combinations."""

from __future__ import annotations

from typing import Any

from .models import CombinationScore, NumberFeatures


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

    # 6. Anti-crowding: penalise numbers that are too clustered
    ac_sc = _anti_crowding_score(nums)

    # 7. Diversity: entropy-like measure over tens groups
    div_sc = _diversity_score(nums)

    total = (
        weights.get("long_frequency", 0.0) * long_freq
        + weights.get("recent_frequency", 0.0) * recent_freq
        + weights.get("gap_score", 0.0) * gap_sc
        + weights.get("pair_score", 0.0) * pair_sc
        + weights.get("distribution_score", 0.0) * dist_sc
        + weights.get("anti_crowding", 0.0) * ac_sc
        + weights.get("diversity", 0.0) * div_sc
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
    """Average normalised pair frequency for all pairs in combo."""
    if total_draws == 0:
        return 0.5
    pairs = []
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            key = (nums[i], nums[j])
            freq = pair_freq.get(key, 0)
            # Expected under uniform: total_draws * C(6,2)/C(45,2) ≈ total * 15/990
            expected = total_draws * 15 / 990
            pairs.append(freq / (expected + 1e-9))
    avg = sum(pairs) / len(pairs) if pairs else 0.0
    # Normalise: score around 1.0 is average; cap at 2.0
    return min(avg / 2.0, 1.0)


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


def _anti_crowding_score(nums: list[int]) -> float:
    """Penalise combinations where numbers cluster tightly."""
    # Count numbers within 3 of each other
    crowded_pairs = 0
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[j] - nums[i] <= 3:
                crowded_pairs += 1
    max_pairs = 5  # rough normalisation
    return max(0.0, 1.0 - crowded_pairs / max_pairs)


def _diversity_score(nums: list[int]) -> float:
    """Entropy-like score based on spread across tens groups (1-9, 10-19, ...)."""
    from collections import Counter
    import math
    groups = Counter((n - 1) // 10 for n in nums)  # 0-4
    total = 6
    entropy = -sum((c / total) * math.log(c / total) for c in groups.values())
    max_entropy = math.log(min(5, 6))  # at most 5 groups
    return entropy / max_entropy if max_entropy > 0 else 0.0
