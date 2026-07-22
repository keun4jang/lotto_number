"""Portfolio construction: select final games with diversity + coverage constraints.

수학적 사실:
- 개별 티켓의 당첨 확률은 고정이며 어떤 선택 방식으로도 바뀌지 않는다.
- 서로 다른 k개 조합 = 정확히 k/8,145,060 의 1등 적중 확률 (중복 조합 무의미).
- 커버리지/겹침 최적화는 하위 등수 결과의 분산 구조만 바꾸며 EV는 불변.
통계 기반 추천, EV 관점 비인기 조합 회피, 당첨 보장 없음.
"""

from __future__ import annotations

from typing import Any

from .analyzer import compute_number_features, compute_pair_frequency
from .coverage import build_abbreviated_wheel
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
    pf_cfg = cfg.get("portfolio", {})
    coverage_weight: float = pf_cfg.get("coverage_weight", 0.05)
    candidate_pool: int = pf_cfg.get("candidate_pool", 200)

    all_candidates = generate_candidates(draws, cfg, seed)
    number_features = compute_number_features(draws, cfg)
    pair_freq = compute_pair_frequency(draws)
    total_draws = len(draws)
    prev_draw = draws[-1] if draws else None

    # Score each strategy pool and pick best per strategy
    selected_combos: list[tuple[str, list[int]]] = []  # (strategy, numbers)

    for strategy, n_games in strategy_game_counts.items():
        candidates = all_candidates.get(strategy, [])
        if not candidates:
            continue
        scored = score_candidates(
            candidates, strategy, number_features, pair_freq, total_draws, cfg,
            prev_draw=prev_draw,
        )

        # Coverage-aware greedy: among the top `candidate_pool` scored
        # candidates that satisfy the diversity constraint, pick the one
        # maximizing score - coverage_weight * (normalized overlap with
        # already-selected games). Purely a variance-structure choice:
        # per-ticket probability and EV are unchanged.
        picked = 0
        while picked < n_games:
            current_games = [g for _, g in selected_combos]
            existing_sets = [frozenset(g) for g in current_games]
            best: tuple[float, tuple[int, ...]] | None = None
            for cs in scored[:candidate_pool]:
                nums = tuple(cs.numbers)
                num_set = frozenset(nums)
                # Zero-duplicate guarantee: identical 6-number sets impossible
                if num_set in existing_sets:
                    continue
                if not _check_new_game_diversity(list(nums), current_games, max_overlap):
                    continue
                total_ov = sum(len(num_set & es) for es in existing_sets)
                penalty = (
                    coverage_weight * total_ov / (6 * len(existing_sets))
                    if existing_sets
                    else 0.0
                )
                objective = cs.total_score - penalty
                if best is None or objective > best[0]:
                    best = (objective, nums)
            if best is None:
                # Fallback: scan the rest of the scored list in order
                for cs in scored[candidate_pool:]:
                    nums = tuple(cs.numbers)
                    if frozenset(nums) in existing_sets:
                        continue
                    if _check_new_game_diversity(list(nums), current_games, max_overlap):
                        best = (cs.total_score, nums)
                        break
            if best is None:
                break
            selected_combos.append((strategy, list(best[1])))
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


def build_wheel_portfolio(
    draws: list[Draw],
    cfg: dict[str, Any],
    seed: int,
    run_id: int,
) -> tuple[list[RecommendationGame], list[CandidateNumber], float]:
    """축약 휠 모드: TOP-N 후보 번호에서 K게임 축약 휠을 구성한다.

    N=12, K=5 에서는 완전 3-guarantee 가 수학적으로 불가능하므로
    (220 트리플 vs 최대 100 커버) best-effort 최대 커버리지를 구성하고
    달성률을 반환한다. 휠링은 하위 등수 결과 분포(분산)만 바꾸며
    티켓당 확률·EV는 절대 바뀌지 않는다. 당첨 보장 없음.

    Returns (games, candidate_numbers, achieved_3subset_coverage).
    """
    pf_cfg = cfg.get("portfolio", {})
    pool_size: int = pf_cfg.get("wheel_pool_size", 12)
    num_games: int = cfg["generator"]["num_games"]

    top_numbers = select_top_numbers(draws, cfg, seed, top_k=max(pool_size, 10))
    pool = [n for n, _ in top_numbers[:pool_size]]

    wheel_games, coverage = build_abbreviated_wheel(pool, num_games)

    labels = [chr(ord("A") + i) for i in range(len(wheel_games))]
    games = [
        RecommendationGame(
            run_id=run_id,
            game_label=labels[i],
            strategy="wheel",
            numbers=sorted(nums),
        )
        for i, nums in enumerate(wheel_games)
    ]

    candidate_numbers = [
        CandidateNumber(run_id=run_id, number=n, score=score, rank=rank + 1)
        for rank, (n, score) in enumerate(top_numbers[:10])
    ]
    return games, candidate_numbers, coverage


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
