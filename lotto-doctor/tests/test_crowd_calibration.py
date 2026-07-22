"""Tests for crowd_calibration.py — 실측 인기도 보정 데이터셋/회귀.

당첨 확률과 무관 — 기대 공동 당첨자 수(인기도) 추정 로직만 검증한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from lotto_doctor.crowd_calibration import (
    FIRST_1000_WON_DRAW,
    TOTAL_COMBINATIONS,
    CalibrationRow,
    build_calibration_dataset,
    expected_first_winners,
    extract_features,
    fit_popularity_regression,
    model_measurement_correlation,
)
from lotto_doctor.models import Draw


def _draw(no, numbers, sales=50_000_000_000, winners=6):
    return Draw(
        draw_no=no,
        draw_date=date(2010, 1, 1),
        numbers=sorted(numbers),
        bonus=45 if 45 not in numbers else 44,
        total_sales=sales,
        first_winners=winners,
        first_amount=1_000_000_000,
    )


def test_expected_first_winners():
    # 8,145,060 게임 판매 = 정확히 1.0 기대 당첨자
    assert expected_first_winners(TOTAL_COMBINATIONS * 1000) == pytest.approx(1.0)
    assert expected_first_winners(0) == 0.0


def test_extract_features_keys_and_values():
    f = extract_features([1, 2, 3, 4, 5, 6])
    assert f["count_le_12"] == 6.0
    assert f["arithmetic"] == pytest.approx(1.0)
    assert f["consecutive_pairs"] == 5.0
    f2 = extract_features([33, 38, 40, 41, 43, 45])
    assert f2["count_le_12"] == 0.0
    assert f2["count_13_31"] == 0.0
    # prev overlap
    f3 = extract_features([1, 2, 3, 40, 41, 45], prev_numbers=[1, 2, 3, 4, 5, 6])
    assert f3["prev_overlap"] > 0.0


def test_build_dataset_excludes_2000_won_era_and_low_expected():
    draws = [
        _draw(50, [1, 5, 9, 20, 30, 40]),                     # 2,000원 시대 → 제외
        _draw(200, [2, 6, 11, 21, 33, 42]),                   # 포함
        _draw(201, [3, 8, 13, 25, 36, 44], sales=1_000_000),  # 기대<1 → 제외
        _draw(202, [4, 9, 15, 27, 38, 45]),                   # 포함
    ]
    rows = build_calibration_dataset(draws)
    assert [r.draw_no for r in rows] == [200, 202]
    assert all(r.draw_no >= FIRST_1000_WON_DRAW for r in rows)
    assert all(r.expected_winners >= 1.0 for r in rows)


def test_calibration_row_log_ratio_sign():
    sales = TOTAL_COMBINATIONS * 1000 * 5  # expected = 5
    over = build_calibration_dataset([_draw(300, [1, 9, 20, 27, 38, 45], sales=sales, winners=20)])
    under = build_calibration_dataset([_draw(300, [1, 9, 20, 27, 38, 45], sales=sales, winners=1)])
    assert over[0].log_ratio > 0 > under[0].log_ratio
    assert over[0].weight == pytest.approx(5.0)


def test_prev_draw_feature_uses_previous_numbers():
    draws = [
        _draw(500, [1, 2, 3, 4, 5, 6]),
        _draw(501, [1, 2, 3, 4, 5, 7]),
    ]
    rows = build_calibration_dataset(draws)
    r501 = [r for r in rows if r.draw_no == 501][0]
    assert r501.features["prev_overlap"] == 1.0  # 5개 겹침 → 상한 1.0


def test_fit_regression_recovers_planted_effect():
    """count_le_12 에 심어 놓은 효과를 회귀가 복원해야 한다."""
    import random

    rng = random.Random(7)
    draws = []
    for i in range(400):
        nums = rng.sample(range(1, 46), 6)
        c12 = sum(1 for n in nums if n <= 12)
        winners = max(0, round(6 * (1 + 0.15 * c12) + rng.gauss(0, 1)))
        draws.append(_draw(200 + i, nums, sales=6 * TOTAL_COMBINATIONS * 1000, winners=winners))
    rows = build_calibration_dataset(draws)
    res = fit_popularity_regression(rows, feature_names=["count_le_12"])
    coef, se, p = res["count_le_12"]
    assert coef > 0.05
    assert p < 0.01


def test_model_measurement_correlation_shape():
    draws = [_draw(200 + i, sorted(__import__("random").Random(i).sample(range(1, 46), 6)))
             for i in range(30)]
    rows = build_calibration_dataset(draws)
    pe, sp = model_measurement_correlation(rows)
    assert -1.0 <= pe <= 1.0
    assert -1.0 <= sp <= 1.0
    assert model_measurement_correlation(rows[:2]) == (0.0, 0.0)


def test_dataset_is_pure_and_deterministic():
    draws = [_draw(200 + i, [1 + i % 5, 8, 17, 26, 35, 44 - i % 3]) for i in range(10)]
    a = build_calibration_dataset(draws)
    b = build_calibration_dataset(draws)
    assert a == b
    assert all(isinstance(r, CalibrationRow) for r in a)
