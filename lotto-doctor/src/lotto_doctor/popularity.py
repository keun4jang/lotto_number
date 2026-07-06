"""EV/anti-popularity features for Lotto Doctor.

로또에서 당첨 확률은 모든 조합이 동일하다.
이 모듈은 사람들이 많이 선택할 가능성이 높은 조합을 측정하여
당첨 시 공동 당첨자 수를 줄일 수 있는 EV 관점의 조합을 찾는 데 사용한다.
"""

from __future__ import annotations

import math
from itertools import combinations


# ---------------------------------------------------------------------------
# 번호별 구매자 인기 가중치
# ---------------------------------------------------------------------------

_NUMBER_POPULARITY: dict[int, float] = {n: (1.5 if n <= 31 else 1.0) for n in range(1, 46)}
_NUMBER_POPULARITY.update({
    1: 1.9, 3: 1.8, 6: 1.7, 7: 2.2, 11: 1.6, 13: 0.65,
    14: 2.1, 21: 2.1, 22: 1.6, 28: 2.1, 33: 0.85,
})

# 너무 유명한 "패턴 조합" — 구매자가 많이 고를 가능성이 높은 조합
_FAMOUS_PATTERNS: list[tuple[int, ...]] = [
    (1, 2, 3, 4, 5, 6),
    (2, 4, 6, 8, 10, 12),
    (5, 10, 15, 20, 25, 30),
    (7, 14, 21, 28, 35, 42),
    (1, 11, 21, 31, 41, 42),
    (6, 12, 18, 24, 30, 36),
    (10, 20, 30, 40, 41, 42),
    (1, 7, 14, 21, 28, 35),
]


# ---------------------------------------------------------------------------
# 조합 인기도 피처
# ---------------------------------------------------------------------------

def birthday_count(nums: list[int]) -> int:
    """1~31 번호 개수 (생일 효과)."""
    return sum(1 for n in nums if n <= 31)


def all_birthday(nums: list[int]) -> bool:
    """모든 번호가 31 이하."""
    return all(n <= 31 for n in nums)


def high_number_count(nums: list[int]) -> int:
    """32~45 번호 개수."""
    return sum(1 for n in nums if n >= 32)


def consecutive_pair_count(nums: list[int]) -> int:
    """연속 번호 쌍 개수."""
    s = sorted(nums)
    return sum(1 for i in range(len(s) - 1) if s[i + 1] - s[i] == 1)


def max_consecutive_run(nums: list[int]) -> int:
    """최장 연속 번호 길이."""
    s = sorted(nums)
    max_run = 1
    current = 1
    for i in range(1, len(s)):
        if s[i] - s[i - 1] == 1:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 1
    return max_run


def same_last_digit_max(nums: list[int]) -> int:
    """끝자리가 같은 번호의 최대 개수."""
    from collections import Counter
    counts = Counter(n % 10 for n in nums)
    return max(counts.values())


def same_tens_max(nums: list[int]) -> int:
    """십의 자리가 같은 번호의 최대 개수."""
    from collections import Counter
    counts = Counter(n // 10 for n in nums)
    return max(counts.values())


def multiple_of_7_count(nums: list[int]) -> int:
    """7의 배수 번호 개수."""
    return sum(1 for n in nums if n % 7 == 0)


def arithmetic_pattern_score(nums: list[int]) -> float:
    """등차수열에 가까울수록 1에 가까운 점수."""
    s = sorted(nums)
    gaps = [s[i + 1] - s[i] for i in range(len(s) - 1)]
    if not gaps:
        return 0.0
    mean_gap = sum(gaps) / len(gaps)
    variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
    # 분산이 0에 가까울수록(등차에 가까울수록) 점수 1
    return math.exp(-variance / 5.0)


def regular_spacing_score(nums: list[int]) -> float:
    """번호 간격이 지나치게 균일한 정도."""
    s = sorted(nums)
    gaps = [s[i + 1] - s[i] for i in range(len(s) - 1)]
    if not gaps:
        return 0.0
    std = math.sqrt(sum((g - sum(gaps) / len(gaps)) ** 2 for g in gaps) / len(gaps))
    return math.exp(-std / 3.0)


def famous_pattern_penalty(nums: list[int]) -> float:
    """유명 패턴이면 1, 아니면 0."""
    t = tuple(sorted(nums))
    return 1.0 if t in _FAMOUS_PATTERNS else 0.0


def too_pretty_balance_score(nums: list[int]) -> float:
    """홀짝 3:3, 저고 3:3, 합계 중앙값 근처 — 지나치게 균형 잡힌 조합일수록 높은 점수."""
    odd = sum(1 for n in nums if n % 2 == 1)
    low = sum(1 for n in nums if n <= 22)
    total = sum(nums)

    odd_balanced = 1.0 if odd == 3 else 0.5 if odd in (2, 4) else 0.0
    low_balanced = 1.0 if low == 3 else 0.5 if low in (2, 4) else 0.0

    # 합계 중앙값 기준: 전체 평균 135 근처
    total_center = 1.0 - min(abs(total - 135) / 50.0, 1.0)

    return (odd_balanced + low_balanced + total_center) / 3.0


def human_pick_popularity_score(nums: list[int]) -> float:
    """높을수록 사람이 많이 고를 가능성이 큰 조합. [0,1]."""
    pop = sum(_NUMBER_POPULARITY.get(n, 1.0) for n in nums) / 6
    # 정규화: 최솟값=0.65, 최댓값=2.2
    normalized = (pop - 0.65) / (2.2 - 0.65)

    pattern = famous_pattern_penalty(nums)
    arithmetic = arithmetic_pattern_score(nums)
    pretty = too_pretty_balance_score(nums)
    all_bday = 1.0 if all_birthday(nums) else 0.0
    consec = min(consecutive_pair_count(nums) / 3.0, 1.0)

    score = (
        0.40 * normalized
        + 0.15 * pattern
        + 0.15 * arithmetic
        + 0.15 * pretty
        + 0.10 * all_bday
        + 0.05 * consec
    )
    return max(0.0, min(1.0, score))


def unpopularity_score(nums: list[int]) -> float:
    """높을수록 EV 관점에서 비인기 조합 (당첨 시 공동 당첨자 감소 가능성). [0,1]."""
    return 1.0 - human_pick_popularity_score(nums)
