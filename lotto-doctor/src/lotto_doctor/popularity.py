"""EV/anti-popularity model for Lotto Doctor.

로또 6/45에서 모든 조합의 당첨 확률은 정확히 동일하다 (1 / 8,145,060).
이 모듈은 당첨 확률을 바꾸려는 것이 아니다 — 그것은 불가능하다.

한국 로또 1~3등은 패리뮤추얼(pari-mutuel) 방식으로 당첨자끼리 상금을
나눈다. 따라서 "사람들이 많이 고르는 조합"을 피하면 당첨 시 기대 공동
당첨자 수가 줄어 조건부 기댓값(EV)이 높아진다. 이 모듈은 그 목적으로
인간의 번호 선택 편향을 모델링해 조합의 '인기도'를 추정한다.
(통계 기반 추천, EV 관점 비인기 조합 회피 — 당첨 보장 없음.)

모델링한 편향과 일반 연구 근거:

1. 생일 편향 — 1~31(특히 월/일 모두 가능한 1~12)이 과선택되고 32~45는
   과소선택된다. Cook & Clotfelter (1993, AER) "The Peculiar Scale
   Economies of Lotto"; Simon (1998, J. Risk & Uncertainty) 영국 로또
   조합 선택 분포 분석.
2. 행운/기피 숫자 — 한국에서 7이 가장 선호되고 3, 8도 선호된다.
   4(사死 기피)와 13(서양권 기피)은 과소선택된다. 문화권별 숫자 선호
   연구 및 복권 판매 데이터 분석 관행.
3. 용지 시각 패턴 — 한국 로또 마킹 용지는 한 줄에 7개씩(7열) 번호가
   배열되므로, 같은 행/열/대각선/지그재그/클러스터로 마킹된 조합이
   과선택된다. Henze & Riedwyl (1998) "How to Win More" 의 스위스·독일
   로또 용지 기하 패턴 분석과 같은 원리.
4. 직전 회차 번호 재선택 — 직전 당첨번호를 그대로/일부 따라 사는 행동.
   Clotfelter & Cook (1993, Management Science) 의 핫넘버 추종 현상.
5. 등차수열·유명 조합 — (1,2,3,4,5,6), 7의 배수열 등은 무작위 대비
   수천 배 과선택된다 (Simon 1998; Riedwyl의 스위스 로또 관측).
6. 끝자리 0 소폭 기피, 지나치게 '균형 잡힌' 조합 과선택 — Farrell,
   Hartley, Lanot & Walker (2000, Oxf. Bull. Econ. Stat.); Baker &
   McHale (2009, JRSS-A) 영국 로또 당첨금 분포 모형.

주의: 아래 가중치들은 판매 데이터가 공개되지 않는 한국 로또에 대한
근사치이며, 위 문헌들이 보고한 편향의 방향/상대 크기를 따른다.
"""

from __future__ import annotations

import math
from collections import Counter
from itertools import combinations

# ---------------------------------------------------------------------------
# 용지(마킹 시트) 기하: 번호 1~45 는 7열 그리드에 배열된다.
#   row = (n - 1) // 7, col = (n - 1) % 7  (마지막 행은 43~45 세 칸)
# ---------------------------------------------------------------------------

_GRID_COLS = 7


def _grid_pos(n: int) -> tuple[int, int]:
    """용지 상의 (행, 열) 좌표."""
    return divmod(n - 1, _GRID_COLS)


# ---------------------------------------------------------------------------
# 번호별 상대 인기 가중치 (평균 1.0 으로 정규화)
# ---------------------------------------------------------------------------

def _build_number_popularity() -> dict[int, float]:
    """편향 문헌 기반 번호별 상대 선택률 테이블 생성.

    승법(multiplicative) 모형: 생일 구간 기본값 × 행운/기피 조정.
    절대값이 아니라 상대 비율만 의미가 있으므로 평균 1.0 으로 정규화한다.
    """
    w: dict[int, float] = {}
    for n in range(1, 46):
        # (1) 생일 편향: 1~12 는 '월'과 '일' 모두로 선택됨 → 최고 인기
        if n <= 12:
            base = 1.60
        elif n <= 31:
            base = 1.32
        else:
            base = 0.72  # 생일로 불가능한 32~45 는 뚜렷하게 과소선택
        # (2) 행운 숫자: 7 최고 인기, 3·8 선호, 7의 배수도 선호
        if n == 7:
            base *= 1.40
        elif n in (3, 8):
            base *= 1.15
        elif n % 7 == 0:  # 14, 21, 28, 35, 42
            base *= 1.12
        # 반복 자릿수(11, 22, 33)는 시각적으로 선호
        if n in (11, 22, 33):
            base *= 1.06
        # (3) 기피 숫자: 4(사死), 44, 13
        if n == 4:
            base *= 0.87
        elif n == 44:
            base *= 0.90
        elif n == 13:
            base *= 0.85
        # (4) 끝자리 0 은 소폭 과소선택
        if n % 10 == 0:
            base *= 0.93
        w[n] = base
    mean = sum(w.values()) / len(w)
    return {n: round(v / mean, 6) for n, v in w.items()}


#: 번호별 상대 인기 가중치 (평균 1.0). generator/features 에서도 공유한다.
NUMBER_POPULARITY: dict[int, float] = _build_number_popularity()

# 하위 호환: 기존 내부 이름 유지
_NUMBER_POPULARITY = NUMBER_POPULARITY

_SORTED_WEIGHTS = sorted(NUMBER_POPULARITY.values())
_MIN_MEAN6 = sum(_SORTED_WEIGHTS[:6]) / 6.0    # 가장 비인기 6개 평균
_MAX_MEAN6 = sum(_SORTED_WEIGHTS[-6:]) / 6.0   # 가장 인기 6개 평균


# ---------------------------------------------------------------------------
# 유명 "패턴 조합" — 대량 중복 구매가 관측/보고되는 조합들
# ---------------------------------------------------------------------------

_FAMOUS_PATTERNS: list[tuple[int, ...]] = [
    (1, 2, 3, 4, 5, 6),          # 가장 유명한 조합 (Simon 1998)
    (2, 4, 6, 8, 10, 12),        # 짝수열
    (5, 10, 15, 20, 25, 30),     # 5의 배수열
    (7, 14, 21, 28, 35, 42),     # 7의 배수열 (행운 숫자 + 용지 세로줄)
    (3, 6, 9, 12, 15, 18),       # 3의 배수열
    (6, 12, 18, 24, 30, 36),     # 6의 배수열
    (1, 11, 21, 31, 41, 42),
    (10, 20, 30, 40, 41, 42),
    (1, 7, 14, 21, 28, 35),
    (4, 8, 15, 16, 23, 42),      # 드라마 'Lost' 조합 — 전 세계적 과선택
    (40, 41, 42, 43, 44, 45),    # 끝 구간 연속열
]

_FAMOUS_PATTERN_SETS: list[frozenset[int]] = [frozenset(p) for p in _FAMOUS_PATTERNS]


# ---------------------------------------------------------------------------
# 조합 인기도 피처 (개별)
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
    counts = Counter(n % 10 for n in nums)
    return max(counts.values())


def same_tens_max(nums: list[int]) -> int:
    """십의 자리가 같은 번호의 최대 개수."""
    counts = Counter(n // 10 for n in nums)
    return max(counts.values())


def multiple_of_7_count(nums: list[int]) -> int:
    """7의 배수 번호 개수."""
    return sum(1 for n in nums if n % 7 == 0)


def number_bias_score(nums: list[int]) -> float:
    """번호 자체의 인기(생일/행운 숫자 편향) 평균을 [0,1] 로 정규화.

    1.0 = 가장 인기 있는 6개 번호로만 구성, 0.0 = 가장 비인기 6개.
    """
    mean_w = sum(NUMBER_POPULARITY[n] for n in nums) / len(nums)
    span = _MAX_MEAN6 - _MIN_MEAN6
    if span <= 0:
        return 0.5
    return max(0.0, min(1.0, (mean_w - _MIN_MEAN6) / span))


def grid_line_score(nums: list[int]) -> float:
    """용지(7열 그리드)에서 같은 행/열/대각선 위 번호의 최대 개수 → [0,1].

    3개 이상이 한 직선 위에 있으면 시각적 '줄 긋기' 패턴으로 간주.
    (Henze & Riedwyl 1998 의 용지 기하 패턴)
    """
    rows: Counter = Counter()
    cols: Counter = Counter()
    diag: Counter = Counter()   # ↘ 대각선: row - col 동일
    anti: Counter = Counter()   # ↙ 대각선: row + col 동일
    for n in nums:
        r, c = _grid_pos(n)
        rows[r] += 1
        cols[c] += 1
        diag[r - c] += 1
        anti[r + c] += 1
    m = max(
        max(rows.values()),
        max(cols.values()),
        max(diag.values()),
        max(anti.values()),
    )
    return min(max(m - 2, 0) / 4.0, 1.0)


def grid_cluster_score(nums: list[int]) -> float:
    """용지에서 인접 칸(상하좌우/대각) 쌍의 개수 → [0,1].

    붙어 있는 칸을 덩어리/지그재그로 마킹하는 습관을 포착한다.
    번호 차이 1(가로), 7(세로), 6/8(대각)이 인접 칸에 해당.
    """
    pos = [_grid_pos(n) for n in nums]
    pairs = 0
    for (r1, c1), (r2, c2) in combinations(pos, 2):
        if max(abs(r1 - r2), abs(c1 - c2)) == 1:
            pairs += 1
    return min(pairs / 5.0, 1.0)


def arithmetic_pattern_score(nums: list[int]) -> float:
    """등차수열에 가까울수록 1에 가까운 점수.

    간격 분산이 0(완전 등차)이면 1.0. 분산이 커질수록 지수적으로 감소.
    5,10,15,... 같은 '규칙 간격' 조합의 과선택을 포착한다.
    """
    s = sorted(nums)
    gaps = [s[i + 1] - s[i] for i in range(len(s) - 1)]
    if not gaps:
        return 0.0
    mean_gap = sum(gaps) / len(gaps)
    variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
    # 1.5 스케일: 진짜 등차(분산~0)만 높게, 단순 밀집 조합은 낮게.
    return math.exp(-variance / 1.5)


def regular_spacing_score(nums: list[int]) -> float:
    """번호 간격이 지나치게 균일한 정도 (하위 호환용 보조 피처)."""
    s = sorted(nums)
    gaps = [s[i + 1] - s[i] for i in range(len(s) - 1)]
    if not gaps:
        return 0.0
    std = math.sqrt(sum((g - sum(gaps) / len(gaps)) ** 2 for g in gaps) / len(gaps))
    return math.exp(-std / 3.0)


def famous_pattern_penalty(nums: list[int]) -> float:
    """유명 패턴과 완전 일치 1.0, 5개 이상 겹치면 0.6, 아니면 0."""
    s = frozenset(nums)
    for p in _FAMOUS_PATTERN_SETS:
        overlap = len(s & p)
        if overlap == 6:
            return 1.0
        if overlap >= 5:
            return 0.6
    return 0.0


def long_run_score(nums: list[int]) -> float:
    """3개 이상 연속 번호(용지 가로 줄긋기·1,2,3식 선택) → [0,1]."""
    run = max_consecutive_run(nums)
    return min(max(run - 2, 0) / 4.0, 1.0)


def prev_draw_overlap_score(nums: list[int], prev_numbers: list[int] | None) -> float:
    """직전 회차 당첨번호와의 겹침 → [0,1]. 직전 번호 재구매 편향 포착."""
    if not prev_numbers:
        return 0.0
    overlap = len(set(nums) & set(prev_numbers))
    return min(overlap / 4.0, 1.0)


def too_pretty_balance_score(nums: list[int]) -> float:
    """홀짝 3:3, 저고 3:3, 합계 중앙값 근처 — 지나치게 '균형 잡힌' 조합.

    사람들은 무작위처럼 '보이는' 균형 조합을 선호한다 (Farrell et al. 2000).
    """
    odd = sum(1 for n in nums if n % 2 == 1)
    low = sum(1 for n in nums if n <= 22)
    total = sum(nums)

    odd_balanced = 1.0 if odd == 3 else 0.5 if odd in (2, 4) else 0.0
    low_balanced = 1.0 if low == 3 else 0.5 if low in (2, 4) else 0.0

    # 합계 기준점 135: 이론 평균(138)보다 약간 낮게 — 생일 편향으로
    # 구매자 합계 분포가 저번호 쪽으로 치우치는 점을 반영.
    total_center = 1.0 - min(abs(total - 135) / 50.0, 1.0)

    return (odd_balanced + low_balanced + total_center) / 3.0


def birthday_dominance_score(nums: list[int]) -> float:
    """조합 차원의 생일 지배도: 6개 전부 1~31이면 1.0, 5개면 0.5.

    번호별 생일 가중치와 별개로, '날짜만으로 만든 조합'(생일 6개 마킹)
    이라는 조합 수준 효과를 추가로 포착한다 (Cook & Clotfelter 1993).
    """
    b = birthday_count(nums)
    if b >= 6:
        return 1.0
    if b == 5:
        return 0.5
    return 0.0


# ---------------------------------------------------------------------------
# 합성 인기도 / 비인기도 점수
# ---------------------------------------------------------------------------

#: 합성 가중치 — 합계 1.0. number_bias 가 지배적(생일+행운 숫자 효과가
#: 문헌상 가장 큰 편향)이고, 나머지는 조합 수준 패턴 효과.
_COMPONENT_WEIGHTS: dict[str, float] = {
    "number_bias": 0.34,     # 생일/행운 숫자 편향 (가장 강한 효과)
    "grid_line": 0.10,       # 용지 행/열/대각선 패턴
    "grid_cluster": 0.06,    # 용지 인접 칸 클러스터/지그재그
    "arithmetic": 0.12,      # 등차수열 패턴
    "famous": 0.10,          # 유명 조합 (1,2,3,4,5,6 등)
    "pretty": 0.10,          # 지나치게 균형 잡힌 조합
    "birthday_combo": 0.08,  # 6개 전부 생일 범위
    "long_run": 0.06,        # 3+ 연속 번호
    "prev_overlap": 0.04,    # 직전 회차 번호 재구매
}


def human_pick_popularity_score(
    nums: list[int],
    prev_numbers: list[int] | None = None,
) -> float:
    """높을수록 사람이 많이 고를 가능성이 큰 조합. [0,1].

    prev_numbers 를 주면 직전 회차 재구매 편향까지 반영한다 (선택).
    """
    w = _COMPONENT_WEIGHTS
    score = (
        w["number_bias"] * number_bias_score(nums)
        + w["grid_line"] * grid_line_score(nums)
        + w["grid_cluster"] * grid_cluster_score(nums)
        + w["arithmetic"] * arithmetic_pattern_score(nums)
        + w["famous"] * famous_pattern_penalty(nums)
        + w["pretty"] * too_pretty_balance_score(nums)
        + w["birthday_combo"] * birthday_dominance_score(nums)
        + w["long_run"] * long_run_score(nums)
        + w["prev_overlap"] * prev_draw_overlap_score(nums, prev_numbers)
    )
    return max(0.0, min(1.0, score))


def unpopularity_score(
    nums: list[int],
    prev_numbers: list[int] | None = None,
) -> float:
    """높을수록 EV 관점의 비인기 조합. [0,1].

    당첨 확률은 동일하지만, 당첨 시 기대 공동 당첨자 수가 적어
    조건부 기댓값이 높을 것으로 추정되는 조합이 높은 점수를 받는다.
    당첨 보장과는 무관하다.
    """
    return 1.0 - human_pick_popularity_score(nums, prev_numbers)
