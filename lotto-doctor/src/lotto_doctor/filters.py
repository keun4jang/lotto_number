"""Combination filters for Lotto Doctor."""

from __future__ import annotations

from typing import Any

from .models import Draw


def passes_all_filters(
    combo: tuple[int, ...] | list[int],
    prev_draw: Draw | None,
    cfg: dict[str, Any],
) -> bool:
    """Return True only if the combination passes every filter."""
    nums = sorted(combo)
    f = cfg.get("filters", {})

    if not _filter_sum(nums, f):
        return False
    if not _filter_odd_count(nums, f):
        return False
    if not _filter_low_count(nums, f):
        return False
    if not _filter_consecutive_pairs(nums, f):
        return False
    if not _filter_same_ending_digit(nums, f):
        return False
    if not _filter_same_tens_digit(nums, f):
        return False
    if not _filter_require_high_number(nums, f):
        return False
    if not _filter_not_arithmetic_sequence(nums):
        return False
    if prev_draw is not None and not _filter_prev_draw_overlap(nums, prev_draw, f):
        return False
    return True


# ---------------------------------------------------------------------------
# Individual filters
# ---------------------------------------------------------------------------


def _filter_sum(nums: list[int], f: dict[str, Any]) -> bool:
    """Sum of numbers must be in [sum_min, sum_max]."""
    s = sum(nums)
    return f.get("sum_min", 90) <= s <= f.get("sum_max", 190)


def _filter_odd_count(nums: list[int], f: dict[str, Any]) -> bool:
    """Number of odd values must be in allowed set."""
    allowed: list[int] = f.get("odd_count_allowed", [2, 3, 4])
    odd_count = sum(1 for n in nums if n % 2 == 1)
    return odd_count in allowed


def _filter_low_count(nums: list[int], f: dict[str, Any]) -> bool:
    """Number of 'low' numbers (1 to low_threshold) must be in allowed set."""
    threshold: int = f.get("low_threshold", 22)
    allowed: list[int] = f.get("low_count_allowed", [2, 3, 4])
    low_count = sum(1 for n in nums if n <= threshold)
    return low_count in allowed


def _filter_consecutive_pairs(nums: list[int], f: dict[str, Any]) -> bool:
    """Number of consecutive pairs must not exceed max_consecutive_pairs."""
    max_pairs: int = f.get("max_consecutive_pairs", 2)
    pairs = sum(
        1 for i in range(len(nums) - 1) if nums[i + 1] - nums[i] == 1
    )
    return pairs <= max_pairs


def _filter_same_ending_digit(nums: list[int], f: dict[str, Any]) -> bool:
    """No more than max_same_ending_digit numbers share the same units digit."""
    from collections import Counter
    max_count: int = f.get("max_same_ending_digit", 2)
    ending_counter = Counter(n % 10 for n in nums)
    return max(ending_counter.values()) <= max_count


def _filter_same_tens_digit(nums: list[int], f: dict[str, Any]) -> bool:
    """No more than max_same_tens_digit numbers share the same tens digit."""
    from collections import Counter
    max_count: int = f.get("max_same_tens_digit", 3)
    tens_counter = Counter((n - 1) // 10 for n in nums)
    return max(tens_counter.values()) <= max_count


def _filter_require_high_number(nums: list[int], f: dict[str, Any]) -> bool:
    """At least one number must be >= high_threshold (default 32)."""
    if not f.get("require_high_number", True):
        return True
    threshold: int = f.get("high_threshold", 32)
    return any(n >= threshold for n in nums)


def _filter_not_arithmetic_sequence(nums: list[int]) -> bool:
    """Reject obvious arithmetic sequences (all differences equal)."""
    diffs = [nums[i + 1] - nums[i] for i in range(len(nums) - 1)]
    if len(set(diffs)) == 1:
        return False  # pure arithmetic sequence
    return True


def _filter_prev_draw_overlap(
    nums: list[int], prev_draw: Draw, f: dict[str, Any]
) -> bool:
    """Overlap with previous draw must not exceed max_prev_draw_overlap."""
    max_overlap: int = f.get("max_prev_draw_overlap", 3)
    overlap = len(set(nums) & set(prev_draw.numbers))
    return overlap <= max_overlap


def check_portfolio_diversity(
    games: list[list[int]], cfg: dict[str, Any]
) -> bool:
    """
    Return True if no two games in the portfolio share more than
    max_game_overlap numbers.
    """
    max_overlap: int = cfg.get("filters", {}).get("max_game_overlap", 2)
    for i in range(len(games)):
        for j in range(i + 1, len(games)):
            overlap = len(set(games[i]) & set(games[j]))
            if overlap > max_overlap:
                return False
    return True
