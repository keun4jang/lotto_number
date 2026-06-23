"""Tests for combination filters."""

import pytest
from lotto_doctor.filters import passes_all_filters, check_portfolio_diversity


BASE_CFG = {
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
    }
}


def test_valid_combo():
    # sum=138, 3 odd, 3 low (<=22), no arithmetic sequence, has 35 >= 32
    combo = (4, 11, 18, 27, 35, 43)
    assert passes_all_filters(combo, None, BASE_CFG) is True


def test_sum_too_low():
    combo = (1, 2, 3, 4, 5, 6)  # sum=21
    assert passes_all_filters(combo, None, BASE_CFG) is False


def test_sum_too_high():
    combo = (40, 41, 42, 43, 44, 45)  # sum=255
    assert passes_all_filters(combo, None, BASE_CFG) is False


def test_all_odd():
    combo = (1, 3, 5, 7, 9, 35)  # 6 odd
    assert passes_all_filters(combo, None, BASE_CFG) is False


def test_all_even():
    combo = (2, 4, 6, 8, 10, 36)  # 6 even
    assert passes_all_filters(combo, None, BASE_CFG) is False


def test_all_low_numbers():
    combo = (1, 5, 10, 15, 20, 22)  # all <=22
    assert passes_all_filters(combo, None, BASE_CFG) is False


def test_no_high_number():
    combo = (5, 10, 15, 20, 25, 30)  # none >=32
    assert passes_all_filters(combo, None, BASE_CFG) is False


def test_all_under_31():
    combo = (5, 10, 15, 20, 25, 31)  # all <=31
    assert passes_all_filters(combo, None, BASE_CFG) is False


def test_arithmetic_sequence_rejected():
    # Use: 7,14,21,28,35,42 (step 7) - pure arithmetic sequence
    combo = (7, 14, 21, 28, 35, 42)
    assert passes_all_filters(combo, None, BASE_CFG) is False


def test_portfolio_diversity_ok():
    games = [
        [1, 2, 3, 4, 5, 33],
        [6, 7, 8, 9, 10, 34],
        [11, 12, 13, 14, 15, 35],
    ]
    assert check_portfolio_diversity(games, BASE_CFG) is True


def test_portfolio_diversity_fail():
    games = [
        [1, 2, 3, 4, 5, 33],
        [1, 2, 3, 7, 8, 34],  # overlaps 3 with game 0
    ]
    assert check_portfolio_diversity(games, BASE_CFG) is False
