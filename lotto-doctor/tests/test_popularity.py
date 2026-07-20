"""Tests for the EV/anti-popularity model (popularity.py).

당첨 확률은 모든 조합이 동일하다. 여기서 검증하는 것은
"사람이 많이 고르는 조합일수록 popularity 가 높고 unpopularity 가
낮아야 한다"는 EV 관점 점수의 방향성뿐이다.
"""

from __future__ import annotations

import pytest

from lotto_doctor.features import _anti_popularity_score
from lotto_doctor.popularity import (
    NUMBER_POPULARITY,
    arithmetic_pattern_score,
    birthday_dominance_score,
    famous_pattern_penalty,
    grid_cluster_score,
    grid_line_score,
    human_pick_popularity_score,
    long_run_score,
    number_bias_score,
    prev_draw_overlap_score,
    unpopularity_score,
)

# 대표 인기 조합 (인간 편향이 강하게 걸린 조합들)
POPULAR_COMBOS = [
    [1, 2, 3, 4, 5, 6],        # 가장 유명한 조합
    [7, 14, 21, 28, 35, 42],   # 7의 배수 (용지 세로줄)
    [1, 7, 14, 21, 28, 35],    # 유명 패턴
    [5, 10, 15, 20, 25, 30],   # 5의 배수 등차수열
    [3, 7, 8, 11, 12, 21],     # 생일+행운 숫자 위주
]

# 대표 비인기 조합 (생일 범위 밖 고번호 위주, 패턴 없음)
UNPOPULAR_COMBOS = [
    [33, 38, 40, 41, 43, 45],
    [32, 36, 39, 43, 44, 45],
    [20, 32, 37, 39, 43, 44],
]


# ---------------------------------------------------------------------------
# 번호별 인기 테이블
# ---------------------------------------------------------------------------

def test_number_popularity_covers_all_numbers():
    assert set(NUMBER_POPULARITY) == set(range(1, 46))
    assert all(w > 0 for w in NUMBER_POPULARITY.values())


def test_number_popularity_mean_normalized():
    mean = sum(NUMBER_POPULARITY.values()) / 45
    assert mean == pytest.approx(1.0, abs=0.01)


def test_lucky_seven_is_most_popular():
    assert NUMBER_POPULARITY[7] == max(NUMBER_POPULARITY.values())


def test_birthday_bands_ordered():
    """1~12 > 13~31 > 32~45 평균 인기 (생일 편향)."""
    band_a = sum(NUMBER_POPULARITY[n] for n in range(1, 13)) / 12
    band_b = sum(NUMBER_POPULARITY[n] for n in range(13, 32)) / 19
    band_c = sum(NUMBER_POPULARITY[n] for n in range(32, 46)) / 14
    assert band_a > band_b > band_c


def test_korean_lucky_numbers_boosted():
    assert NUMBER_POPULARITY[3] > NUMBER_POPULARITY[2]
    assert NUMBER_POPULARITY[8] > NUMBER_POPULARITY[9]


def test_unlucky_numbers_reduced():
    assert NUMBER_POPULARITY[4] < NUMBER_POPULARITY[5]   # 사(死) 기피
    assert NUMBER_POPULARITY[13] < NUMBER_POPULARITY[15]  # 서양 기피


def test_ending_zero_slightly_underpicked():
    assert NUMBER_POPULARITY[40] < NUMBER_POPULARITY[41]
    assert NUMBER_POPULARITY[20] < NUMBER_POPULARITY[19]


# ---------------------------------------------------------------------------
# 개별 피처
# ---------------------------------------------------------------------------

def test_number_bias_score_range_and_ordering():
    for combo in POPULAR_COMBOS + UNPOPULAR_COMBOS:
        assert 0.0 <= number_bias_score(combo) <= 1.0
    assert number_bias_score([1, 3, 7, 8, 11, 12]) > 0.8   # 최고 인기 번호들
    assert number_bias_score([33, 38, 40, 41, 43, 45]) < 0.1


def test_grid_line_score_column_pattern():
    """7의 배수 = 용지 세로줄 (6개 모두 같은 열)."""
    assert grid_line_score([7, 14, 21, 28, 35, 42]) == 1.0


def test_grid_line_score_row_pattern():
    """1~6 은 용지 첫 행에 나란히 있다."""
    assert grid_line_score([1, 2, 3, 4, 5, 6]) == 1.0


def test_grid_line_score_scattered():
    """직선 위에 3개 이상 놓이지 않는 흩어진 조합은 0."""
    assert grid_line_score([1, 9, 20, 27, 38, 45]) == 0.0


def test_grid_cluster_score_block():
    """용지에서 붙어 있는 2x3 블록은 최대 클러스터 점수."""
    assert grid_cluster_score([1, 2, 8, 9, 15, 16]) == 1.0


def test_grid_cluster_score_spread():
    assert grid_cluster_score([1, 10, 19, 28, 37, 45]) <= 0.4


def test_arithmetic_pattern_score_exact():
    assert arithmetic_pattern_score([5, 10, 15, 20, 25, 30]) == pytest.approx(1.0)
    assert arithmetic_pattern_score([1, 2, 3, 4, 5, 6]) == pytest.approx(1.0)


def test_arithmetic_pattern_score_irregular_low():
    # 간격이 불규칙한 조합은 등차 점수가 낮아야 한다
    assert arithmetic_pattern_score([1, 4, 18, 27, 39, 44]) < 0.2


def test_famous_pattern_exact_and_partial():
    assert famous_pattern_penalty([1, 2, 3, 4, 5, 6]) == 1.0
    assert famous_pattern_penalty([1, 2, 3, 4, 5, 45]) == 0.6   # 5개 겹침
    assert famous_pattern_penalty([9, 16, 24, 33, 39, 44]) == 0.0


def test_long_run_score():
    assert long_run_score([1, 2, 3, 4, 5, 6]) == 1.0
    assert long_run_score([10, 11, 12, 25, 33, 44]) == pytest.approx(0.25)
    assert long_run_score([3, 9, 17, 25, 33, 41]) == 0.0
    # 연속 2개(한 쌍)까지는 페널티 없음
    assert long_run_score([3, 9, 17, 25, 40, 41]) == 0.0


def test_birthday_dominance_score():
    assert birthday_dominance_score([1, 5, 9, 14, 22, 31]) == 1.0   # 전부 생일
    assert birthday_dominance_score([1, 5, 9, 14, 22, 40]) == 0.5   # 5개
    assert birthday_dominance_score([1, 5, 9, 14, 38, 40]) == 0.0


def test_prev_draw_overlap_score():
    prev = [2, 9, 16, 23, 30, 37]
    assert prev_draw_overlap_score(prev, prev) == 1.0
    assert prev_draw_overlap_score([2, 9, 40, 41, 43, 45], prev) == pytest.approx(0.5)
    assert prev_draw_overlap_score([1, 3, 40, 41, 43, 45], prev) == 0.0
    assert prev_draw_overlap_score([1, 2, 3, 4, 5, 6], None) == 0.0


# ---------------------------------------------------------------------------
# 합성 점수
# ---------------------------------------------------------------------------

def test_scores_in_unit_interval():
    for combo in POPULAR_COMBOS + UNPOPULAR_COMBOS:
        p = human_pick_popularity_score(combo)
        u = unpopularity_score(combo)
        assert 0.0 <= p <= 1.0
        assert 0.0 <= u <= 1.0
        assert u == pytest.approx(1.0 - p)


def test_popular_combos_score_low_unpopularity():
    """인기 조합의 unpopularity 는 모든 비인기 조합보다 낮아야 한다."""
    worst_unpopular = min(unpopularity_score(c) for c in UNPOPULAR_COMBOS)
    for combo in POPULAR_COMBOS:
        assert unpopularity_score(combo) < worst_unpopular, combo


def test_unpopular_combos_score_high_unpopularity():
    for combo in UNPOPULAR_COMBOS:
        assert unpopularity_score(combo) > 0.65, combo


def test_famous_combo_is_most_popular():
    """(1,2,3,4,5,6) 은 샘플 중 최고 인기(최저 unpopularity)."""
    u_123456 = unpopularity_score([1, 2, 3, 4, 5, 6])
    for combo in POPULAR_COMBOS[1:] + UNPOPULAR_COMBOS:
        assert u_123456 < unpopularity_score(combo)


def test_clear_separation_between_popular_and_unpopular():
    u_pop = unpopularity_score([1, 7, 14, 21, 28, 35])
    u_unpop = unpopularity_score([33, 38, 40, 41, 43, 45])
    assert u_unpop - u_pop > 0.3


def test_prev_draw_overlap_lowers_unpopularity():
    """직전 회차 번호를 그대로 사면 인기 조합으로 간주된다."""
    prev = [8, 17, 23, 32, 39, 44]
    u_without = unpopularity_score(prev)
    u_with = unpopularity_score(prev, prev_numbers=prev)
    assert u_with < u_without


def test_unpopularity_backward_compatible_signature():
    """prev_numbers 없이 호출하는 기존 코드 경로가 그대로 동작해야 한다."""
    combo = [4, 13, 26, 33, 38, 44]
    assert unpopularity_score(combo) == unpopularity_score(combo, prev_numbers=None)


def test_anti_popularity_feature_ordering():
    """features._anti_popularity_score 도 같은 번호 테이블을 공유한다."""
    assert _anti_popularity_score([33, 38, 40, 41, 43, 45]) > _anti_popularity_score(
        [1, 7, 14, 21, 28, 35]
    )
    for combo in POPULAR_COMBOS + UNPOPULAR_COMBOS:
        assert 0.0 <= _anti_popularity_score(combo) <= 1.0
