"""Tests for coverage metrics, wheel construction, and coverage-aware portfolio.

수학적 사실: 커버리지/휠링은 하위 등수 결과의 분산 구조만 바꾸며,
티켓당 당첨 확률과 EV는 절대 바뀌지 않는다. k개의 서로 다른 조합은
정확히 k/8,145,060 의 1등 적중 확률을 가진다.
"""

from __future__ import annotations

from itertools import combinations
from math import comb

from lotto_doctor.coverage import (
    build_abbreviated_wheel,
    format_coverage_line,
    portfolio_coverage_metrics,
    prob_any_game_3plus,
    wheel_3subset_coverage,
)

DISJOINT_5 = [
    [1, 2, 3, 4, 5, 6],
    [7, 8, 9, 10, 11, 12],
    [13, 14, 15, 16, 17, 18],
    [19, 20, 21, 22, 23, 24],
    [25, 26, 27, 28, 29, 30],
]


def test_metrics_disjoint():
    m = portfolio_coverage_metrics(DISJOINT_5)
    assert m["distinct_numbers"] == 30
    assert m["max_pairwise_overlap"] == 0
    assert m["duplicate_games"] == 0
    assert len(m["pairwise_overlaps"]) == 10


def test_metrics_duplicates_and_overlap():
    games = [[1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6], [1, 2, 3, 40, 41, 42]]
    m = portfolio_coverage_metrics(games)
    assert m["duplicate_games"] == 1
    assert m["max_pairwise_overlap"] == 6
    assert m["distinct_numbers"] == 9


def test_prob_any_3plus_overlap_hurts():
    """겹침이 클수록 P(최소 한 게임 3개 이상 적중)이 작아진다 (분산 구조)."""
    identical = [[1, 2, 3, 4, 5, 6]] * 5
    p_disjoint = prob_any_game_3plus(DISJOINT_5, n_samples=40_000, seed=7)
    p_identical = prob_any_game_3plus(identical, n_samples=40_000, seed=7)
    # single-game analytic P(>=3) ~ 0.01864
    p_single = sum(
        comb(6, k) * comb(39, 6 - k) for k in (3, 4, 5, 6)
    ) / comb(45, 6)
    assert abs(p_identical - p_single) < 0.005
    assert p_disjoint > p_identical


def test_wheel_full_guarantee_trivial():
    games, cov = build_abbreviated_wheel([1, 2, 3, 4, 5, 6], k_games=1)
    assert games == [[1, 2, 3, 4, 5, 6]]
    assert cov == 1.0


def test_wheel_no_duplicates_and_honest_coverage():
    pool = list(range(1, 13))  # N=12
    games, cov = build_abbreviated_wheel(pool, k_games=5)
    assert len(games) == 5
    assert len({tuple(g) for g in games}) == 5  # zero duplicates
    for g in games:
        assert len(set(g)) == 6
        assert set(g) <= set(pool)
    # Reported coverage must equal independently recomputed coverage
    assert abs(cov - wheel_3subset_coverage(games, pool)) < 1e-12
    # K=5 covers at most 100/220 triples; greedy should reach close to the cap
    assert cov <= 100 / 220 + 1e-12
    assert cov >= 0.40


def test_wheel_deterministic():
    pool = list(range(1, 13))
    g1, c1 = build_abbreviated_wheel(pool, k_games=5)
    g2, c2 = build_abbreviated_wheel(pool, k_games=5)
    assert g1 == g2 and c1 == c2


def test_wheel_coverage_manual_small_case():
    # pool of 7, one game: covers C(6,3)=20 of C(7,3)=35 triples
    cov = wheel_3subset_coverage([[1, 2, 3, 4, 5, 6]], list(range(1, 8)))
    assert abs(cov - 20 / 35) < 1e-12


def test_format_coverage_line_no_probability_claims():
    m = portfolio_coverage_metrics(DISJOINT_5)
    line = format_coverage_line(m, wheel_coverage=0.455)
    assert "30/30" in line
    assert "45.5%" in line
    assert "확률/EV 향상 아님" in line


def test_portfolio_no_duplicate_games():
    from tests.test_generator import MINIMAL_CFG, _make_draws
    from lotto_doctor.portfolio import build_portfolio

    draws = _make_draws(50)
    games, _ = build_portfolio(draws, MINIMAL_CFG, seed=1234, run_id=1)
    sets = {frozenset(g.numbers) for g in games}
    assert len(sets) == len(games)


def test_portfolio_deterministic_with_coverage_weight():
    from tests.test_generator import MINIMAL_CFG, _make_draws
    from lotto_doctor.portfolio import build_portfolio

    cfg = dict(MINIMAL_CFG)
    cfg["portfolio"] = {"coverage_weight": 0.05, "candidate_pool": 100}
    draws = _make_draws(50)
    g1, _ = build_portfolio(draws, cfg, seed=42, run_id=1)
    g2, _ = build_portfolio(draws, cfg, seed=42, run_id=1)
    assert [g.numbers for g in g1] == [g.numbers for g in g2]


def test_build_wheel_portfolio():
    from tests.test_generator import MINIMAL_CFG, _make_draws
    from lotto_doctor.portfolio import build_wheel_portfolio

    cfg = dict(MINIMAL_CFG)
    cfg["generator"] = dict(cfg["generator"])
    cfg["generator"]["num_games"] = 5
    draws = _make_draws(50)
    games, cands, cov = build_wheel_portfolio(draws, cfg, seed=42, run_id=1)
    assert len(games) == 5
    assert all(g.strategy == "wheel" for g in games)
    assert len({frozenset(g.numbers) for g in games}) == 5
    assert 0.0 < cov <= 100 / 220 + 1e-12
    assert len(cands) == 10
