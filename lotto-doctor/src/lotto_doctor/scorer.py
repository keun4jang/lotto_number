"""Scoring engine for candidate combinations."""

from __future__ import annotations

from typing import Any

from .features import compute_combination_score
from .models import CombinationScore, Draw, NumberFeatures


def score_candidates(
    candidates: list[tuple[int, ...]],
    strategy: str,
    number_features: dict[int, NumberFeatures],
    pair_freq: dict[tuple[int, int], int],
    total_draws: int,
    cfg: dict[str, Any],
    prev_draw: Draw | None = None,
) -> list[CombinationScore]:
    """Score all candidates and return sorted list (best first).

    prev_draw 가 주어지면 EV 점수에 '직전 회차 번호 재구매' 편향
    회피가 반영된다 (없으면 기존 동작과 동일 — 하위 호환).
    """
    scored = [
        compute_combination_score(
            combo=c,
            strategy=strategy,
            number_features=number_features,
            pair_freq=pair_freq,
            total_draws=total_draws,
            cfg=cfg,
            prev_draw=prev_draw,
        )
        for c in candidates
    ]
    scored.sort(key=lambda s: s.total_score, reverse=True)
    return scored
