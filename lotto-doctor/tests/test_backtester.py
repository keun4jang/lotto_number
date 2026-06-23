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
