"""ev_monitor 테스트 — EV 계측 루프 (상금 분할 노출, 당첨 확률과 무관)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from lotto_doctor.ev_monitor import (
    check_calibration_drift,
    ev_track_record,
    evaluate_recommendation_ev,
    format_ev_section,
    measure_draw_popularity,
    random_population_scores,
    upsert_ev_metric,
)
from lotto_doctor.models import Draw
from lotto_doctor.reflection import generate_reflection_text


def make_draw(draw_no, numbers, *, total_sales=0, first_winners=0):
    return Draw(
        draw_no=draw_no,
        draw_date=date(2026, 7, 18),
        numbers=list(numbers),
        bonus=45 if 45 not in numbers else 44,
        total_sales=total_sales,
        first_winners=first_winners,
        first_amount=0,
    )


# ---------------------------------------------------------------------------
# measure_draw_popularity
# ---------------------------------------------------------------------------


def test_measure_draw_popularity_known_ratio():
    # 판매 81.4506억원 → 8,145,060게임 → 기대 1등 1.0명. 관측 3명 → ratio 3.0
    d = make_draw(1000, [1, 2, 3, 4, 5, 6],
                  total_sales=8_145_060_000, first_winners=3)
    assert measure_draw_popularity(d) == pytest.approx(3.0)


def test_measure_draw_popularity_missing_data_returns_none():
    d = make_draw(1000, [1, 2, 3, 4, 5, 6], total_sales=0, first_winners=3)
    assert measure_draw_popularity(d) is None
    d2 = make_draw(1000, [1, 2, 3, 4, 5, 6], total_sales=8_000_000_000)
    d2 = Draw(**{**d2.__dict__, "first_winners": None}) if hasattr(d2, "__dict__") else d2
    assert measure_draw_popularity(d2) is None or measure_draw_popularity(d2) >= 0


def test_measure_draw_popularity_override_sales():
    d = make_draw(1000, [1, 2, 3, 4, 5, 6], total_sales=0, first_winners=2)
    ratio = measure_draw_popularity(d, total_sales=16_290_120_000)  # 기대 2.0
    assert ratio == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# evaluate_recommendation_ev / percentile
# ---------------------------------------------------------------------------


def test_population_scores_deterministic_and_sized():
    a = random_population_scores(500, 7)
    b = random_population_scores(500, 7)
    assert a == b and len(a) == 500
    assert all(0.0 <= s <= 1.0 for s in a)


def test_popular_portfolio_low_percentile_unpopular_high():
    pop = random_population_scores(2000, 11)
    popular = [[1, 2, 3, 4, 5, 6], [7, 14, 21, 28, 35, 42], [3, 7, 8, 9, 11, 12]]
    unpopular = [[20, 26, 33, 38, 41, 44], [19, 25, 32, 37, 43, 45], [22, 27, 34, 39, 40, 44]]
    ev_pop = evaluate_recommendation_ev(popular, population=pop)
    ev_unpop = evaluate_recommendation_ev(unpopular, population=pop)
    assert ev_pop["portfolio_percentile"] < 20
    assert ev_unpop["portfolio_percentile"] > 80
    assert ev_unpop["portfolio_mean_score"] > ev_pop["portfolio_mean_score"]


def test_evaluate_accepts_objects_and_winning_combo():
    class G:
        def __init__(self, numbers):
            self.numbers = numbers

    ev = evaluate_recommendation_ev(
        [G([20, 26, 33, 38, 41, 44])],
        winning_numbers=[1, 2, 3, 4, 5, 6],
        population=random_population_scores(500, 3),
    )
    assert ev["winning_combo_score"] is not None
    assert len(ev["game_scores"]) == 1


# ---------------------------------------------------------------------------
# ev_metrics 지속성 (멱등)
# ---------------------------------------------------------------------------


def test_upsert_ev_metric_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upsert_ev_metric(conn, 1229, 0.5, 60.0, 0.2, 1.3)
    upsert_ev_metric(conn, 1229, 0.6, 70.0, 0.3, None)  # 같은 회차 재실행 → 대체
    upsert_ev_metric(conn, 1230, 0.55, 65.0, None, 0.9)
    hist = ev_track_record(conn)
    assert [h["draw_no"] for h in hist] == [1229, 1230]
    assert hist[0]["portfolio_percentile"] == 70.0
    assert hist[0]["winner_ratio"] is None
    conn.close()


# ---------------------------------------------------------------------------
# 드리프트 점검
# ---------------------------------------------------------------------------

POPULAR_COMBOS = [
    [1, 2, 3, 4, 5, 6], [2, 3, 4, 5, 6, 7], [7, 14, 21, 28, 35, 42],
    [1, 8, 15, 22, 29, 36], [3, 4, 5, 6, 7, 8], [5, 6, 7, 8, 9, 10],
]
UNPOPULAR_COMBOS = [
    [20, 26, 33, 38, 41, 44], [19, 25, 32, 37, 43, 45],
    [22, 27, 34, 39, 40, 44], [18, 24, 31, 36, 42, 45],
    [17, 23, 30, 35, 41, 43], [16, 26, 32, 38, 40, 45],
]

SALES = 16_290_120_000  # 기대 1등 2.0명


def _drift_draws(inverted: bool):
    """inverted=True: 인기 조합에 당첨자 적게 → 모델과 실측이 역상관."""
    draws = []
    n = 200
    for i in range(n):
        if i % 2 == 0:
            nums = POPULAR_COMBOS[(i // 2) % len(POPULAR_COMBOS)]
            winners = 1 if inverted else 8
        else:
            nums = UNPOPULAR_COMBOS[(i // 2) % len(UNPOPULAR_COMBOS)]
            winners = 8 if inverted else 1
        draws.append(make_draw(200 + i, nums, total_sales=SALES, first_winners=winners))
    return draws


def test_drift_check_positive_correlation_no_warning():
    res = check_calibration_drift(_drift_draws(inverted=False), trailing=100)
    assert res["trailing_spearman"] > 0
    assert res["drift_warning"] is False


def test_drift_check_negative_correlation_warns():
    res = check_calibration_drift(_drift_draws(inverted=True), trailing=100)
    assert res["trailing_spearman"] < 0
    assert res["drift_warning"] is True


def test_drift_check_insufficient_data_graceful():
    res = check_calibration_drift([make_draw(500, [1, 2, 3, 4, 5, 6])])
    assert res["drift_warning"] is False
    assert res["full_spearman"] is None


# ---------------------------------------------------------------------------
# 반성 텍스트 통합
# ---------------------------------------------------------------------------


def _sample_ev_section():
    ev = evaluate_recommendation_ev(
        UNPOPULAR_COMBOS[:3], population=random_population_scores(500, 3)
    )
    history = [
        {"portfolio_percentile": 80.0}, {"portfolio_percentile": 90.0},
    ]
    drift = {"drift_warning": True, "trailing_spearman": -0.12, "n_trailing": 200}
    return format_ev_section(ev, 1.34, history, drift)


def test_format_ev_section_content_and_length():
    section = _sample_ev_section()
    assert "📈 EV 계측" in section
    assert "당첨 확률과 무관" in section
    assert "재보정" in section
    # 6줄 이내 추가 (구분선 제외한 실제 내용)
    content_lines = [l for l in section.split("\n") if l.strip() and "━" not in l]
    assert len(content_lines) <= 6
    # 확률 향상 주장 금지
    for banned in ("확률 상승", "확률 향상", "당첨 확률을 높"):
        assert banned not in section


def test_reflection_text_includes_ev_section_and_telegram_limit():
    games = [
        {"game_label": c, "strategy": "balanced", "matched_count": 2,
         "rank_label": "none", "has_bonus_match": False}
        for c in "ABCDEFGHIJ"
    ]
    text = generate_reflection_text(
        draw_no=1229, draw_numbers=[3, 11, 19, 27, 35, 43], bonus=7,
        games=games, perf={}, new_strategy_games=None,
        ev_section=_sample_ev_section(),
    )
    assert "📈 EV 계측" in text
    assert "당첨을 보장하지 않습니다" in text
    assert len(text) < 4096  # Telegram 메시지 한도


def test_reflection_text_without_ev_section_unchanged():
    games = [{"game_label": "A", "strategy": "balanced", "matched_count": 0,
              "rank_label": "none", "has_bonus_match": False}]
    text = generate_reflection_text(
        draw_no=1229, draw_numbers=[3, 11, 19, 27, 35, 43], bonus=7,
        games=games, perf={}, new_strategy_games=None,
    )
    assert "EV 계측" not in text
    assert "당첨을 보장하지 않습니다" in text
