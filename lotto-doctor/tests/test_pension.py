"""Tests for Pension Lottery 720+ modules."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pytest

from lotto_doctor.pension_models import PensionDraw, PensionRecommendationGame
from lotto_doctor.pension_collector import parse_pension_csv, generate_sample_csv
from lotto_doctor.pension_analyzer import get_jo_frequency, get_digit_frequency, get_summary_stats
from lotto_doctor.pension_evaluator import evaluate_pension_run, _count_matching_suffix
from lotto_doctor.pension_database import (
    init_pension_db,
    upsert_pension_draw,
    get_all_pension_draws,
    get_latest_pension_draw_no,
    insert_pension_run,
    insert_pension_game,
    get_pension_games_for_run,
)
from lotto_doctor.pension_models import PensionRecommendationRun


def _make_draws(n: int = 100) -> list[PensionDraw]:
    draws = []
    for i in range(1, n + 1):
        jo = (i % 5) + 1
        number = str(i * 137 % 1000000).zfill(6)
        draws.append(PensionDraw(draw_no=i, draw_date=date(2020, 1, 1), jo=jo, number=number))
    return draws


def test_parse_pension_csv_basic():
    csv_text = "회차,추첨일,조,번호\n1,2021-01-01,3,123456\n2,2021-01-08,1,654321"
    draws = parse_pension_csv(csv_text)
    assert len(draws) == 2
    assert draws[0].draw_no == 1
    assert draws[0].jo == 3
    assert draws[0].number == "123456"
    assert draws[1].draw_no == 2


def test_parse_pension_csv_tab_delimited():
    csv_text = "회차\t추첨일\t조\t번호\n10\t2021-03-06\t2\t999888"
    draws = parse_pension_csv(csv_text)
    assert len(draws) == 1
    assert draws[0].draw_no == 10
    assert draws[0].number == "999888"


def test_generate_sample_csv(tmp_path):
    out = str(tmp_path / "sample.csv")
    generate_sample_csv(out)
    content = Path(out).read_text(encoding="utf-8")
    assert "회차" in content
    assert "번호" in content


def test_jo_frequency():
    draws = _make_draws(10)
    freq = get_jo_frequency(draws)
    assert sum(freq.values()) == 10
    assert all(j in range(1, 6) for j in freq.keys())


def test_digit_frequency_shape():
    draws = _make_draws(50)
    freq = get_digit_frequency(draws)
    assert len(freq) == 6
    for pos_freq in freq:
        assert sum(pos_freq.values()) == 50


def test_summary_stats():
    draws = _make_draws(20)
    stats = get_summary_stats(draws)
    assert stats["total_draws"] == 20
    assert stats["latest_draw_no"] == 20


@pytest.mark.parametrize("rec,act,expected", [
    ("123456", "123456", 6),
    ("123456", "123457", 0),
    ("123456", "113456", 4),
    ("000000", "100000", 5),
    ("000000", "000000", 6),
])
def test_count_matching_suffix(rec, act, expected):
    assert _count_matching_suffix(rec, act) == expected


def test_evaluate_pension_run_1st_prize():
    draw = PensionDraw(draw_no=1, draw_date=date(2021, 1, 1), jo=3, number="123456")
    game = PensionRecommendationGame(run_id=1, game_label="A", strategy="hot", jo=3, number="123456")
    results = evaluate_pension_run([game], draw)
    assert results[0].prize_rank == "1st"
    assert results[0].jo_match is True
    assert results[0].matched_suffix == 6


def test_evaluate_pension_run_2nd_prize():
    draw = PensionDraw(draw_no=1, draw_date=date(2021, 1, 1), jo=3, number="123456")
    game = PensionRecommendationGame(run_id=1, game_label="A", strategy="hot", jo=2, number="123456")
    results = evaluate_pension_run([game], draw)
    assert results[0].prize_rank == "2nd"
    assert results[0].jo_match is False


def test_evaluate_pension_run_no_prize():
    draw = PensionDraw(draw_no=1, draw_date=date(2021, 1, 1), jo=3, number="123456")
    game = PensionRecommendationGame(run_id=1, game_label="A", strategy="hot", jo=2, number="000000")
    results = evaluate_pension_run([game], draw)
    assert results[0].prize_rank == "no_prize")


def test_pension_db_roundtrip():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    init_pension_db(db_path)

    draws = _make_draws(5)
    with sqlite3.connect(db_path) as conn:
        for d in draws:
            upsert_pension_draw(conn, d)
        conn.commit()

    with sqlite3.connect(db_path) as conn:
        loaded = get_all_pension_draws(conn)
        latest = get_latest_pension_draw_no(conn)

    assert len(loaded) == 5
    assert latest == 5


def test_pension_run_and_games():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    init_pension_db(db_path)

    with sqlite3.connect(db_path) as conn:
        run = PensionRecommendationRun(draw_no=100, model_version="pension-v1.0.0", seed=100)
        run_id = insert_pension_run(conn, run)
        game = PensionRecommendationGame(run_id=run_id, game_label="A", strategy="hot", jo=3, number="123456")
        insert_pension_game(conn, game)
        conn.commit()

        games = get_pension_games_for_run(conn, run_id)

    assert len(games) == 1
    assert games[0].game_label == "A"
    assert games[0].jo == 3
    assert games[0].number == "123456"


def test_pension_generator_basic():
    from lotto_doctor.pension_generator import generate_pension_portfolio

    draws = _make_draws(100)
    cfg = {"pension": {"jo_range": 5, "num_games": 3, "recent_window": 50}}
    games = generate_pension_portfolio(draws, cfg, seed=42, run_id=1)

    assert len(games) == 3
    for g in games:
        assert 1 <= g.jo <= 5
        assert len(g.number) == 6
        assert g.number.isdigit()
        assert g.strategy in ["hot", "cold", "balanced"]


def test_pension_generator_deterministic():
    from lotto_doctor.pension_generator import generate_pension_portfolio

    draws = _make_draws(100)
    cfg = {"pension": {"jo_range": 5, "num_games": 3, "recent_window": 50}}
    g1 = generate_pension_portfolio(draws, cfg, seed=99, run_id=1)
    g2 = generate_pension_portfolio(draws, cfg, seed=99, run_id=1)

    for a, b in zip(g1, g2):
        assert a.jo == b.jo
        assert a.number == b.number
