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


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

def _make_draws(n: int = 100) -> list[PensionDraw]:
    draws = []
    for i in range(1, n + 1):
        jo = (i % 5) + 1
        number = str(i * 137 % 1000000).zfill(6)
        draws.append(PensionDraw(draw_no=i, draw_date=date(2020, 1, 1), jo=jo, number=number))
    return draws


# ---------------------------------------------------------------------------
# pension_collector
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# pension_analyzer
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# pension_evaluator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rec,act,expected", [
    ("123456", "123456", 6),
    ("123456", "123457", 0),   # last digit differs
    ("123456", "113456", 4),   # last 4 match (position 1 differs)
    ("000000", "100000", 5),   # last 5 match
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
    assert results[0].prize_rank == "no_prize"


# ---------------------------------------------------------------------------
# pension_database
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# pension_generator
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Regression tests: 소규모/빈 데이터에서의 샘플링 분포 유효성
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("game_number,expected_rank", [
    ("923456", "3rd"),   # 뒤 5자리
    ("993456", "4th"),   # 뒤 4자리
    ("999456", "5th"),   # 뒤 3자리
    ("999956", "6th"),   # 뒤 2자리
    ("999996", "7th"),   # 뒤 1자리
    ("999999", "no_prize"),
])
def test_pension_suffix_prize_ranks(game_number, expected_rank):
    draw = PensionDraw(draw_no=1, draw_date=date(2021, 1, 1), jo=3, number="123456")
    game = PensionRecommendationGame(
        run_id=1, game_label="A", strategy="hot", jo=1, number=game_number
    )
    results = evaluate_pension_run([game], draw)
    assert results[0].prize_rank == expected_rank


def test_count_matching_suffix_is_end_anchored():
    # 길이가 어긋난 입력이라도 '뒤자리' 기준으로 비교해야 한다
    assert _count_matching_suffix("0123456", "123456") == 6
    assert _count_matching_suffix("12345", "912345") == 5


def test_generate_number_empty_data_not_degenerate():
    """Regression: 빈 빈도 데이터에서 hot 전략이 항상 '999999'를 만들었다."""
    import random as _random
    from lotto_doctor.pension_generator import _generate_number

    rng = _random.Random(1)
    empty_freq = [dict() for _ in range(6)]
    digits: list[int] = []
    for _ in range(50):
        digits.extend(int(c) for c in _generate_number(empty_freq, "hot", rng))
    assert len(set(digits)) >= 8   # 균등분포라면 300자리에서 거의 확실히 8종 이상
    assert any(d != 9 for d in digits)


def test_sample_jo_empty_data_not_degenerate():
    """Regression: 빈 데이터에서 hot은 항상 5조, balanced는 5조로 편향됐었다."""
    import random as _random
    from collections import Counter
    from lotto_doctor.pension_generator import _sample_jo

    for strategy in ["hot", "cold", "balanced"]:
        rng = _random.Random(7)
        samples = [_sample_jo({}, strategy, rng) for _ in range(1000)]
        counts = Counter(samples)
        assert set(counts) == {1, 2, 3, 4, 5}, f"{strategy}: 일부 조가 전혀 안 나옴"
        assert max(counts.values()) / 1000 < 0.35, f"{strategy}: 특정 조 편향"


def test_pension_generator_empty_draws_no_crash():
    from lotto_doctor.pension_generator import generate_pension_portfolio

    cfg = {"pension": {"jo_range": 5, "num_games": 5, "recent_window": 50}}
    games = generate_pension_portfolio([], cfg, seed=1, run_id=1)
    assert len(games) == 5
    for g in games:
        assert 1 <= g.jo <= 5
        assert len(g.number) == 6
        assert g.number.isdigit()


def test_digit_weights_always_valid_distribution():
    from lotto_doctor.pension_analyzer import digit_weights

    w_empty = digit_weights({})
    assert abs(sum(w_empty) - 1.0) < 1e-9
    assert all(x >= 0 for x in w_empty)

    w = digit_weights({0: 3, 5: 7})
    assert abs(sum(w) - 1.0) < 1e-9
    assert all(x >= 0 for x in w)
