"""Tests for backtester with small sample."""

from __future__ import annotations

import random
from datetime import date

import pytest

from lotto_doctor.backtester import run_backtest
from lotto_doctor.models import Draw


MINIMAL_CFG = {
    "app": {"model_name": "balanced-ensemble", "model_version": "be-v1.0.0"},
    "generator": {
        "total_candidates": 500,
        "num_games": 10,
        "strategy_counts": {
            "balanced": 200,
            "recent": 100,
            "gap": 100,
            "anti_crowding": 50,
            "random_quality": 50,
        },
        "strategy_games": {
            "balanced": 4,
            "recent": 2,
            "gap": 2,
            "anti_crowding": 1,
            "random_quality": 1,
        },
    },
    "scoring": {
        "weights": {
            "balanced": {
                "long_frequency": 0.20,
                "recent_frequency": 0.20,
                "gap_score": 0.15,
                "pair_score": 0.15,
                "distribution_score": 0.15,
                "anti_crowding": 0.10,
                "diversity": 0.05,
            },
            "recent": {
                "long_frequency": 0.10,
                "recent_frequency": 0.40,
                "gap_score": 0.15,
                "pair_score": 0.10,
                "distribution_score": 0.10,
                "anti_crowding": 0.10,
                "diversity": 0.05,
            },
            "gap": {
                "long_frequency": 0.10,
                "recent_frequency": 0.10,
                "gap_score": 0.40,
                "pair_score": 0.10,
                "distribution_score": 0.10,
                "anti_crowding": 0.15,
                "diversity": 0.05,
            },
            "anti_crowding": {
                "long_frequency": 0.15,
                "recent_frequency": 0.15,
                "gap_score": 0.10,
                "pair_score": 0.10,
                "distribution_score": 0.15,
                "anti_crowding": 0.30,
                "diversity": 0.05,
            },
            "random_quality": {
                "long_frequency": 0.15,
                "recent_frequency": 0.15,
                "gap_score": 0.15,
                "pair_score": 0.15,
                "distribution_score": 0.20,
                "anti_crowding": 0.10,
                "diversity": 0.10,
            },
        }
    },
    "features": {"recent_windows": [20, 50, 100], "gap_max_normalize": 50},
    "filters": {
        "sum_min": 90,
        "sum_max": 190,
        "odd_count_allowed": [2, 3, 4],
        "low_count_allowed": [2, 3, 4],
        "low_threshold": 22,
        "max_consecutive_pairs": 2,
        "max_same_ending_digit": 2,
        "max_same_tens_digit": 3,
        "require_high_number": True,
        "high_threshold": 32,
        "max_prev_draw_overlap": 3,
        "max_game_overlap": 2,
    },
    "backtester": {
        "min_train_draws": 10,
        "report_path": "reports/backtest_summary.md",
    },
}


def _make_draws(n: int = 20) -> list[Draw]:
    rng = random.Random(77)
    draws = []
    for i in range(1, n + 1):
        nums = sorted(rng.sample(range(1, 46), 6))
        bonus = rng.choice([x for x in range(1, 46) if x not in nums])
        draws.append(Draw(
            draw_no=i,
            draw_date=date(2022, 1, i % 28 + 1),
            numbers=nums,
            bonus=bonus,
        ))
    return draws


def test_backtest_runs_and_returns_results():
    draws = _make_draws(15)
    results = run_backtest(draws, MINIMAL_CFG)
    # Should have results for draws 10..14 (min_train=10)
    assert len(results) >= 1


def test_backtest_result_fields():
    draws = _make_draws(15)
    results = run_backtest(draws, MINIMAL_CFG)
    for r in results:
        assert r.draw_no > 0
        assert r.matched_3 >= 0
        assert r.matched_4 >= 0
        assert r.matched_5 >= 0
        assert r.matched_5b >= 0
        assert r.matched_6 >= 0


def test_backtest_match_counts_bounded():
    draws = _make_draws(15)
    results = run_backtest(draws, MINIMAL_CFG)
    for r in results:
        total = r.matched_3 + r.matched_4 + r.matched_5 + r.matched_5b + r.matched_6
        assert total <= 10  # at most 10 games


def _result_tuple(r):
    return (r.matched_3, r.matched_4, r.matched_5, r.matched_5b, r.matched_6)


def test_backtest_no_future_leakage():
    """draws[i]에 대한 결과는 미래 회차(draws[i+1:])의 존재 여부와 무관해야 한다."""
    draws = _make_draws(15)
    full = {r.draw_no: _result_tuple(r) for r in run_backtest(draws, MINIMAL_CFG)}
    partial = {r.draw_no: _result_tuple(r) for r in run_backtest(draws[:11], MINIMAL_CFG)}

    # partial은 draw_no 11 하나만 평가 가능 (min_train=10)
    assert set(partial) == {dn for dn in full if dn <= 11}
    for dn, v in partial.items():
        assert full[dn] == v, f"draw {dn}: 미래 데이터 유무에 따라 결과가 달라짐 (leakage)"


def test_backtest_input_order_does_not_matter():
    """입력 순서가 뒤섞여도 walk-forward는 회차 순으로 정렬되어 동일해야 한다."""
    draws = _make_draws(15)
    r1 = [(r.draw_no, _result_tuple(r)) for r in run_backtest(draws, MINIMAL_CFG)]
    r2 = [(r.draw_no, _result_tuple(r)) for r in run_backtest(list(reversed(draws)), MINIMAL_CFG)]
    assert r1 == r2


def test_random_games_baseline_valid():
    """Regression: _random_games가 passes_all_filters 인자 순서를 바꿔 호출해 크래시했었다."""
    from lotto_doctor.backtester import _random_games
    from lotto_doctor.filters import passes_all_filters

    draws = _make_draws(12)
    games = _random_games(draws, MINIMAL_CFG, seed=123, n_games=5)
    assert len(games) == 5
    for g in games:
        assert len(g) == 6
        assert len(set(g)) == 6
        assert all(1 <= n <= 45 for n in g)
        assert passes_all_filters(g, draws[-1], MINIMAL_CFG)
