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

경험적 보정 (be-v1.3.0-ev, 2026-07):
    한국 실측 데이터로 모델을 보정했다. 회차별 1등 당첨자 수와 판매액에서
    popularity_ratio = 실제 1등 당첨자 수 / (판매 게임 수 / 8,145,060)
    를 계산하면, 그 회차 당첨 조합이 실제 한국 구매자들 사이에서 얼마나
    인기 있었는지에 대한 직접 측정치가 된다 (crowd_calibration.py 참조,
    106~1229회차 약 1,128표본). 주요 발견:
    - 1~12(생일 '월' 구간) 과선택 확인 (번호당 log-ratio +0.049, p<0.001).
    - 등차수열 패턴 과선택 강하게 확인 (계수 +0.71, p<0.0001).
    - 13~31 vs 32~45 구간 차이는 통계적으로 유의하지 않음 — 자동(반자동
      포함) 구매 비중이 높아 조합 인기 편차가 크게 희석되기 때문.
    - 4/13 기피는 유의하게 확인되지 않음 (방향은 사전 문헌 유지).
    이에 따라 NUMBER_POPULARITY 는 문헌 기반 사전값과 경험적 구간
    테이블의 기하 블렌드(λ=0.85)로 축소 보정했고, _COMPONENT_WEIGHTS 는
    등차수열/번호 편향 중심으로 재배분했다. 보정 후 모델 점수와 실측
    log-ratio 의 상관은 Pearson 0.041 → 0.124 로 개선됐다.
    (당첨 확률과 무관 — 기대 공동 당첨자 수 추정만 개선한다.)
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

# 한국 실측 보정: 구간(tier)별 경험적 상대 인기 (crowd_calibration WLS 결과).
# 1~12: exp(+0.049)≈1.044, 13~31: exp(-0.019)≈0.975, 32~45: 기준 1.0
# (평균 1.0 정규화 전 값). 7은 소폭 추가 선호를 유지한다.
_EMPIRICAL_TIER: dict[str, float] = {
    "month": 1.043805,   # 1~12
    "day": 0.975186,     # 13~31
    "high": 0.993892,    # 32~45
}
_EMPIRICAL_BLEND: float = 0.85  # λ: 경험 테이블 비중 (기하 블렌드)


def _empirical_tier_weight(n: int) -> float:
    if n <= 12:
        w = _EMPIRICAL_TIER["month"]
    elif n <= 31:
        w = _EMPIRICAL_TIER["day"]
    else:
        w = _EMPIRICAL_TIER["high"]
    if n == 7:
        w *= 1.03  # 행운의 7: 실측에서도 양의 방향 (유의수준 미달, 소폭 유지)
    return w


def _build_number_popularity() -> dict[int, float]:
    """편향 문헌 기반 번호별 상대 선택률 테이블 생성.

    승법(multiplicative) 모형: 생일 구간 기본값 × 행운/기피 조정.
    절대값이 아니라 상대 비율만 의미가 있으므로 평균 1.0 으로 정규화한다.

    be-v1.3.0-ev: 최종 테이블은 이 문헌 기반 사전값(prior)과 한국 실측
    구간 테이블의 기하 블렌드다 — w = prior^(1-λ) × empirical^λ, λ=0.85.
    실측 데이터는 자동 구매 희석으로 문헌 대비 훨씬 작은 편차를 보이므로
    사전값의 서열(순서)은 유지하되 크기를 경험적 스케일로 축소한다.
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
        # 한국 실측 보정: 사전값과 경험 구간 테이블의 기하 블렌드
        lam = _EMPIRICAL_BLEND
        w[n] = (base ** (1.0 - lam)) * (_empirical_tier_weight(n) ** lam)
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

#: 합성 가중치 — 합계 1.0. be-v1.3.0-ev 에서 한국 실측 데이터(1등 당첨자
#: 수 대 판매량 기반 popularity ratio)에 대한 비음수 회귀(NNLS)로 재보정.
#: 실측에서 유의한 것은 등차수열 패턴(최강)과 번호 편향(1~12 과선택),
#: 그리고 약하게 '균형 잡힌' 조합 선호였다. famous 는 당첨 표본에 등장할
#: 수 없어(유명 조합이 당첨된 적 없음) 데이터로 추정 불가 → 문헌 기반
#: 가중치를 유지한다. 나머지는 실측에서 유의하지 않아 소폭으로 축소.
_COMPONENT_WEIGHTS: dict[str, float] = {
    "number_bias": 0.33,     # 생일/행운 숫자 편향 (실측 확인: 1~12 과선택)
    "grid_line": 0.03,       # 용지 행/열/대각선 패턴 (실측 유의하지 않음)
    "grid_cluster": 0.01,    # 용지 인접 칸 클러스터 (실측 유의하지 않음)
    "arithmetic": 0.42,      # 등차수열 패턴 (실측 최강 신호, p<0.0001)
    "famous": 0.08,          # 유명 조합 — 당첨 표본에서 관측 불가, 문헌 유지
    "pretty": 0.06,          # 균형 잡힌 조합 (실측 약한 양의 신호)
    "birthday_combo": 0.02,  # 6개 전부 생일 범위 (number_bias 에 흡수됨)
    "long_run": 0.02,        # 3+ 연속 번호 (실측 유의하지 않음)
    "prev_overlap": 0.03,    # 직전 회차 번호 재구매 (실측 음의 방향, 축소)
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
