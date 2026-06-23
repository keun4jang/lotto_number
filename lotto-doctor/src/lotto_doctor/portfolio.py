"""Portfolio construction: select final 10 games with diversity constraints."""

from __future__ import annotations

from typing import Any

from .analyzer import compute_number_features, compute_pair_frequency
from .filters import check_portfolio_diversity
from .generator import generate_candidates, select_top_numbers
from .models import CandidateNumber, CombinationScore, Draw, RecommendationGame
from .scorer import score_candidates


def build_portfolio(
    draws: list[Draw],
    cfg: dict[str, Any],
    seed: int,
    run_id: int,
) -> tuple[list[RecommendationGame], list[CandidateNumber]]:
    """
    Generate candidates, score them, and pick the final portfolio of 10 games.
    Returns (games, candidate_numbers).
    """
    strategy_game_counts: dict[str, int] = cfg["generator"]["strategy_games"]
    max_overlap: int = cfg["filters"]["max_game_overlap"]

    all_candidates = generate_candidates(draws, cfg, seed)
    number_features = compute_number_features(draws, cfg)
    pair_freq = compute_pair_frequency(draws)
    total_draws = len(draws)

    # Score each strategy pool and pick best per strategy
    selected_combos: list[tuple[str, list[int]]] = []  # (strategy, numbers)

    for strategy, n_games in strategy_game_counts.items():
        candidates = all_candidates.get(strategy, [])
        if not candidates:
            continue
        scored = score_candidates(
            candidates, strategy, number_features, pair_freq, total_draws, cfg
        )

        # Greedily pick n_games with diversity constraint against already-selected
        picked = 0
        for cs in scored:
            if picked >= n_games:
                break
            candidate_nums = list(cs.numbers)
            current_games = [g for _, g in selected_combos]
            if _check_new_game_diversity(candidate_nums, current_games, max_overlap):
                selected_combos.append((strategy, candidate_nums))
                picked += 1

    # Assign labels A-J
    labels = [chr(ord("A") + i) for i in range(10)]
    games: list[RecommendationGame] = []
    for idx, (strategy, nums) in enumerate(selected_combos[:10]):
        label = labels[idx] if idx < len(labels) else str(idx)
        games.append(
            RecommendationGame(
                run_id=run_id,
                game_label=label,
                strategy=strategy,
                numbers=sorted(nums),
            )
        )

    # Top 10 candidate numbers
    top_numbers = select_top_numbers(draws, cfg, seed, top_k=10)
    candidate_numbers: list[CandidateNumber] = [
        CandidateNumber(run_id=run_id, number=n, score=score, rank=rank + 1)
        for rank, (n, score) in enumerate(top_numbers)
    ]

    return games, candidate_numbers


def _check_new_game_diversity(
    new_game: list[int],
    existing_games: list[list[int]],
    max_overlap: int,
) -> bool:
    """Return True if new_game overlaps at most max_overlap numbers with each existing game."""
    new_set = set(new_game)
    for existing in existing_games:
        if len(new_set & set(existing)) > max_overlap:
            return False
    return True
