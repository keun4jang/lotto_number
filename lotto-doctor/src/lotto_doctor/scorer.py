"""Scoring engine for candidate combinations."""

from __future__ import annotations

from typing import Any

from .features import compute_combination_score
from .models import CombinationScore, NumberFeatures


def score_candidates(
    candidates: list[tuple[int, ...]],
    strategy: str,
    number_features: dict[int, NumberFeatures],
    pair_freq: dict[tuple[int, int], int],
    total_draws: int,
    cfg: dict[str, Any],
) -> list[CombinationScore]:
    """Score all candidates and return sorted list (best first)."""
    scored = [
        compute_combination_score(
            combo=c,
            strategy=strategy,
            number_features=number_features,
            pair_freq=pair_freq,
            total_draws=total_draws,
            cfg=cfg,
        )
        for c in candidates
    ]
    scored.sort(key=lambda s: s.total_score, reverse=True)
    return scored
