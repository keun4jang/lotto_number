"""Walk-forward backtesting for Lotto Doctor."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from .filters import passes_all_filters
from .models import BacktestRun, Draw
from .portfolio import build_portfolio
from .evaluator import evaluate_run


def _random_games(
    draws: list[Draw],
    cfg: dict[str, Any],
    seed: int,
    n_games: int = 10,
) -> list[list[int]]:
    """Generate n_games random valid games for comparison baseline."""
    rng = random.Random(seed)
    prev_draw = draws[-1] if draws else None
    games: list[list[int]] = []
    attempts = 0
    while len(games) < n_games and attempts < 10_000:
        attempts += 1
        combo = sorted(rng.sample(range(1, 46), 6))
        if passes_all_filters(combo, prev_draw, cfg):
            games.append(combo)
    return games


def run_backtest(
    draws: list[Draw],
    cfg: dict[str, Any],
) -> list[BacktestRun]:
    """
    Walk-forward backtest.
    For each draw after min_train_draws, use all prior draws to generate
    recommendations, then evaluate against the actual draw.
    """
    min_train: int = cfg["backtester"]["min_train_draws"]
    results: list[BacktestRun] = []

    # Walk-forward 보장: 회차 오름차순 정렬 (train은 항상 test보다 과거 회차만 포함)
    draws = sorted(draws, key=lambda d: d.draw_no)

    for i in range(min_train, len(draws)):
        train_draws = draws[:i]
        test_draw = draws[i]
        seed = test_draw.draw_no

        # Build a temporary run_id placeholder (0 for backtest)
        try:
            games, _ = build_portfolio(train_draws, cfg, seed, run_id=0)
        except Exception:
            continue

        eval_results = evaluate_run(games, test_draw)

        bt = BacktestRun(draw_no=test_draw.draw_no)
        for ev in eval_results:
            if ev.matched_count == 3:
                bt.matched_3 += 1
            elif ev.matched_count == 4:
                bt.matched_4 += 1
            elif ev.matched_count == 5 and ev.has_bonus_match:
                bt.matched_5b += 1
            elif ev.matched_count == 5:
                bt.matched_5 += 1
            elif ev.matched_count == 6:
                bt.matched_6 += 1

        results.append(bt)

    return results


def generate_backtest_report(
    results: list[BacktestRun],
    report_path: str | Path,
) -> None:
    """Write backtest summary markdown report."""
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    total_3 = sum(r.matched_3 for r in results)
    total_4 = sum(r.matched_4 for r in results)
    total_5 = sum(r.matched_5 for r in results)
    total_5b = sum(r.matched_5b for r in results)
    total_6 = sum(r.matched_6 for r in results)

    draws_with_3 = sum(1 for r in results if r.matched_3 > 0)
    draws_with_4 = sum(1 for r in results if r.matched_4 > 0)
    draws_with_5 = sum(1 for r in results if r.matched_5 > 0)

    lines = [
        "# Lotto Doctor — Backtest Summary",
        "",
        "> 이 결과는 과거 데이터를 이용한 walk-forward 백테스트이며, 미래 당첨을 보장하지 않습니다.",
        "> 정상적인 로또에서 모든 6개 번호 조합의 1등 확률은 동일합니다.",
        "",
        f"## 총 테스트 회차: {total}",
        "",
        "| 적중 | 총 게임 수 | 회차 수 |",
        "|------|-----------|---------|",
        f"| 3개  | {total_3} | {draws_with_3} |",
        f"| 4개  | {total_4} | {draws_with_4} |",
        f"| 5개  | {total_5} | {draws_with_5} |",
        f"| 5개+보너스 | {total_5b} | {sum(1 for r in results if r.matched_5b > 0)} |",
        f"| 6개  | {total_6} | {sum(1 for r in results if r.matched_6 > 0)} |",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
