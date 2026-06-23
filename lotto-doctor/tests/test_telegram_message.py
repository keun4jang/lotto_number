"""Tests for Telegram message formatting."""

from __future__ import annotations

from lotto_doctor.telegram_bot import (
    DISCLAIMER,
    build_recommendation_message,
    build_result_message,
    _split_message,
)
from lotto_doctor.models import Draw, EvaluationResult, RecommendationGame
from datetime import date


def _make_games() -> list[RecommendationGame]:
    games = []
    strategies = ["balanced", "balanced", "balanced", "balanced",
                  "recent", "recent", "gap", "gap", "anti_crowding", "random_quality"]
    for i, strategy in enumerate(strategies):
        label = chr(ord("A") + i)
        nums = sorted([(i * 5 + j + 1) % 45 + 1 for j in range(6)])
        nums = sorted(set(nums))
        while len(nums) < 6:
            nums.append(max(nums) + 1)
        nums = sorted(nums[:6])
        games.append(RecommendationGame(
            run_id=1, game_label=label, strategy=strategy, numbers=nums
        ))
    return games


def test_disclaimer_in_recommendation_message():
    games = _make_games()
    top_nums = [(n, 0.5) for n in range(1, 11)]
    msg = build_recommendation_message(
        target_draw_no=1234,
        candidate_numbers=top_nums,
        games=games,
        summary={"총 학습 회차": 100},
    )
    assert "정상적인 로또에서 모든 6개 번호 조합의 1등 확률은 동일합니다" in msg
    assert "당첨을 보장하지 않습니다" in msg


def test_recommendation_message_contains_draw_no():
    games = _make_games()
    top_nums = [(n, 0.5) for n in range(1, 11)]
    msg = build_recommendation_message(1234, top_nums, games, {})
    assert "1234" in msg


def test_recommendation_message_contains_all_game_labels():
    games = _make_games()
    top_nums = [(n, 0.5) for n in range(1, 11)]
    msg = build_recommendation_message(1234, top_nums, games, {})
    for label in "ABCDEFGHIJ":
        assert label in msg


def test_disclaimer_in_result_message():
    draw = Draw(draw_no=1234, draw_date=date(2024, 1, 1),
                numbers=[1, 2, 3, 4, 5, 6], bonus=7)
    games = _make_games()
    results = [
        EvaluationResult(run_id=1, game_label=g.game_label,
                         matched_count=0, rank_label="no_prize", has_bonus_match=False)
        for g in games
    ]
    msg = build_result_message(draw, games, results, {})
    assert "정상적인 로또에서 모든 6개 번호 조합의 1등 확률은 동일합니다" in msg


def test_split_message_short():
    text = "Hello, World!"
    parts = _split_message(text, max_len=4096)
    assert len(parts) == 1
    assert parts[0] == text


def test_split_message_long():
    text = "\n".join(["Line " + str(i) for i in range(500)])
    parts = _split_message(text, max_len=1000)
    assert len(parts) > 1
    for p in parts:
        assert len(p) <= 1000
