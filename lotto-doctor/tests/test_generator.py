"""Tests for the recommendation generator."""

from __future__ import annotations

import pytest
from datetime import date

from lotto_doctor.models import Draw
from lotto_doctor.portfolio import build_portfolio


MINIMAL_CFG = {
    "app": {"model_name": "balanced-ensemble", "model_version": "be-v1.0.0"},
    "generator": {
        "total_candidates": 1000,
        "num_games": 10,
        "strategy_counts": {
            "balanced": 400,
            "recent": 200,
            "gap": 200,
            "anti_crowding": 100,
            "random_quality": 100,
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
}


def _make_draws(n: int = 50) -> list[Draw]:
    """Create synthetic draw history."""
    import random
    rng = random.Random(42)
    draws = []
    for i in range(1, n + 1):
        nums = sorted(rng.sample(range(1, 46), 6))
        bonus = rng.choice([x for x in range(1, 46) if x not in nums])
        draws.append(Draw(
            draw_no=i,
            draw_date=date(2022, 1, 1),
            numbers=nums,
            bonus=bonus,
        ))
    return draws


def test_generates_10_games():
    draws = _make_draws(50)
    games, candidates = build_portfolio(draws, MINIMAL_CFG, seed=1234, run_id=1)
    assert len(games) == 10


def test_each_game_has_6_numbers():
    draws = _make_draws(50)
    games, _ = build_portfolio(draws, MINIMAL_CFG, seed=1234, run_id=1)
    for g in games:
        assert len(g.numbers) == 6


def test_numbers_in_range():
    draws = _make_draws(50)
    games, _ = build_portfolio(draws, MINIMAL_CFG, seed=1234, run_id=1)
    for g in games:
        for n in g.numbers:
            assert 1 <= n <= 45


def test_no_duplicate_numbers_in_game():
    draws = _make_draws(50)
    games, _ = build_portfolio(draws, MINIMAL_CFG, seed=1234, run_id=1)
    for g in games:
        assert len(set(g.numbers)) == 6


def test_max_overlap_between_games():
    draws = _make_draws(50)
    games, _ = build_portfolio(draws, MINIMAL_CFG, seed=1234, run_id=1)
    max_overlap = MINIMAL_CFG["filters"]["max_game_overlap"]
    for i in range(len(games)):
        for j in range(i + 1, len(games)):
            overlap = len(set(games[i].numbers) & set(games[j].numbers))
            assert overlap <= max_overlap, (
                f"Games {games[i].game_label} and {games[j].game_label} "
                f"share {overlap} numbers (max {max_overlap})"
            )


def test_same_seed_same_result():
    draws = _make_draws(50)
    games1, _ = build_portfolio(draws, MINIMAL_CFG, seed=9999, run_id=1)
    games2, _ = build_portfolio(draws, MINIMAL_CFG, seed=9999, run_id=1)
    for g1, g2 in zip(games1, games2):
        assert g1.numbers == g2.numbers


def test_different_seed_different_result():
    draws = _make_draws(50)
    games1, _ = build_portfolio(draws, MINIMAL_CFG, seed=1, run_id=1)
    games2, _ = build_portfolio(draws, MINIMAL_CFG, seed=2, run_id=1)
    # At least one game should differ (overwhelmingly likely)
    all_same = all(g1.numbers == g2.numbers for g1, g2 in zip(games1, games2))
    assert not all_same
