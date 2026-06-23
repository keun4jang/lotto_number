"""Tests for prize rank evaluation."""

from __future__ import annotations

import pytest
from datetime import date

from lotto_doctor.evaluator import compute_rank, evaluate_game, summarise_evaluation
from lotto_doctor.models import Draw, EvaluationResult, RecommendationGame


def _draw(numbers: list[int], bonus: int) -> Draw:
    return Draw(draw_no=1, draw_date=date(2024, 1, 1), numbers=sorted(numbers), bonus=bonus)


def _game(numbers: list[int]) -> RecommendationGame:
    return RecommendationGame(run_id=1, game_label="A", strategy="balanced", numbers=sorted(numbers))


def test_rank_1st():
    assert compute_rank(6, False) == "1st"


def test_rank_2nd():
    assert compute_rank(5, True) == "2nd"


def test_rank_3rd():
    assert compute_rank(5, False) == "3rd"


def test_rank_4th():
    assert compute_rank(4, False) == "4th"


def test_rank_5th():
    assert compute_rank(3, False) == "5th"


def test_no_prize():
    assert compute_rank(2, False) == "no_prize"
    assert compute_rank(0, False) == "no_prize"


def test_evaluate_game_6_match():
    draw = _draw([1, 2, 3, 4, 5, 6], bonus=7)
    game = _game([1, 2, 3, 4, 5, 6])
    result = evaluate_game(game, draw)
    assert result.matched_count == 6
    assert result.rank_label == "1st"


def test_evaluate_game_5_bonus():
    draw = _draw([1, 2, 3, 4, 5, 6], bonus=7)
    game = _game([1, 2, 3, 4, 5, 7])
    result = evaluate_game(game, draw)
    assert result.matched_count == 5
    assert result.has_bonus_match is True
    assert result.rank_label == "2nd"


def test_evaluate_game_no_prize():
    draw = _draw([1, 2, 3, 4, 5, 6], bonus=7)
    game = _game([10, 20, 30, 33, 40, 45])
    result = evaluate_game(game, draw)
    assert result.matched_count == 0
    assert result.rank_label == "no_prize"


def test_summarise_evaluation():
    results = [
        EvaluationResult(run_id=1, game_label="A", matched_count=3, rank_label="5th", has_bonus_match=False),
        EvaluationResult(run_id=1, game_label="B", matched_count=2, rank_label="no_prize", has_bonus_match=False),
        EvaluationResult(run_id=1, game_label="C", matched_count=4, rank_label="4th", has_bonus_match=False),
    ]
    summary = summarise_evaluation(results)
    assert summary["best_match"] == 4
    assert summary["prize_count"] == 2
