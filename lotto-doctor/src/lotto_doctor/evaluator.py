"""Evaluate recommendation results against actual draw results."""

from __future__ import annotations

from .models import Draw, EvaluationResult, RecommendationGame


RANK_LABELS = {
    (6, False): "1st",
    (5, True): "2nd",
    (5, False): "3rd",
    (4, False): "4th",
    (3, False): "5th",
}


def compute_rank(matched_count: int, has_bonus_match: bool) -> str:
    """Return rank label for given match count and bonus flag."""
    key = (matched_count, has_bonus_match and matched_count == 5)
    if matched_count == 6:
        return "1st"
    if matched_count == 5 and has_bonus_match:
        return "2nd"
    if matched_count == 5:
        return "3rd"
    if matched_count == 4:
        return "4th"
    if matched_count == 3:
        return "5th"
    return "no_prize"


def evaluate_game(game: RecommendationGame, draw: Draw) -> EvaluationResult:
    """Evaluate a single game against an actual draw."""
    game_set = set(game.numbers)
    draw_set = set(draw.numbers)
    matched_count = len(game_set & draw_set)
    has_bonus_match = draw.bonus in game_set
    rank_label = compute_rank(matched_count, has_bonus_match)
    return EvaluationResult(
        run_id=game.run_id,
        game_label=game.game_label,
        matched_count=matched_count,
        rank_label=rank_label,
        has_bonus_match=has_bonus_match,
    )


def evaluate_run(
    games: list[RecommendationGame],
    draw: Draw,
) -> list[EvaluationResult]:
    """Evaluate all games in a run against an actual draw."""
    return [evaluate_game(g, draw) for g in games]


def summarise_evaluation(results: list[EvaluationResult]) -> dict[str, int | str]:
    """Return summary statistics for a set of evaluation results."""
    if not results:
        return {"best_match": 0, "prize_count": 0}
    best = max(r.matched_count for r in results)
    prizes = sum(1 for r in results if r.rank_label != "no_prize")
    rank_counts: dict[str, int] = {}
    for r in results:
        rank_counts[r.rank_label] = rank_counts.get(r.rank_label, 0) + 1
    return {
        "best_match": best,
        "prize_count": prizes,
        "rank_counts": rank_counts,  # type: ignore[dict-item]
    }
