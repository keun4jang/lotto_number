"""Pension Lottery 720+ recommendation generator.

Strategies:
  hot     - favor digits/jo that appeared most recently
  cold    - favor digits/jo that appeared least recently (gap strategy)
  balanced - mix of hot and cold
"""

from __future__ import annotations

import random
from typing import Any

from .pension_analyzer import digit_weights, get_digit_frequency, get_digit_frequency_recent, get_jo_frequency
from .pension_models import PensionDraw, PensionRecommendationGame

_LABELS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

PENSION_STRATEGIES = ["hot", "cold", "balanced"]
PENSION_NUM_GAMES = 3  # default games per strategy set


def _invert_weights(weights: list[float]) -> list[float]:
    """Invert weights so rare items get higher probability."""
    inv = [1.0 / (w + 1e-6) for w in weights]
    total = sum(inv) or 1.0
    return [v / total for v in inv]


def _sample_digit(weights: list[float], rng: random.Random) -> int:
    """Sample a digit 0-9 given weights."""
    r = rng.random()
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            return i
    return 9


def _sample_jo(jo_freq: dict[int, int], strategy: str, rng: random.Random, jo_range: int = 5) -> int:
    jos = list(range(1, jo_range + 1))
    counts = [jo_freq.get(j, 0) for j in jos]
    total = sum(counts) or 1
    weights = [c / total for c in counts]

    if strategy == "cold":
        weights = _invert_weights(weights)
    elif strategy == "balanced":
        uniform = [1.0 / len(jos)] * len(jos)
        weights = [(a + b) / 2 for a, b in zip(weights, uniform)]

    r = rng.random()
    cumulative = 0.0
    for jo, w in zip(jos, weights):
        cumulative += w
        if r <= cumulative:
            return jo
    return jos[-1]


def _generate_number(digit_freq: list[dict[int, int]], strategy: str, rng: random.Random) -> str:
    digits = []
    for pos_freq in digit_freq:
        total = sum(pos_freq.values()) or 1
        base_weights = [pos_freq.get(d, 0) / total for d in range(10)]

        if strategy == "hot":
            weights = base_weights
        elif strategy == "cold":
            weights = _invert_weights(base_weights)
        else:  # balanced
            uniform = [0.1] * 10
            weights = [(a + b) / 2 for a, b in zip(base_weights, uniform)]
            total_w = sum(weights) or 1.0
            weights = [w / total_w for w in weights]

        digits.append(str(_sample_digit(weights, rng)))
    return "".join(digits)


def generate_pension_portfolio(
    draws: list[PensionDraw],
    cfg: dict[str, Any],
    seed: int,
    run_id: int,
) -> list[PensionRecommendationGame]:
    """Generate pension lottery recommendations."""
    rng = random.Random(seed)

    pension_cfg = cfg.get("pension", {})
    num_games: int = pension_cfg.get("num_games", PENSION_NUM_GAMES)
    jo_range: int = pension_cfg.get("jo_range", 5)
    recent_n: int = pension_cfg.get("recent_window", 50)

    jo_freq = get_jo_frequency(draws)
    digit_freq_all = get_digit_frequency(draws)
    digit_freq_recent = get_digit_frequency_recent(draws, recent_n) if len(draws) >= recent_n else digit_freq_all

    games: list[PensionRecommendationGame] = []
    label_idx = 0

    strategies = PENSION_STRATEGIES * (num_games // len(PENSION_STRATEGIES) + 1)
    strategies = strategies[:num_games]

    for strategy in strategies:
        freq = digit_freq_recent if strategy == "hot" else digit_freq_all
        jo = _sample_jo(jo_freq, strategy, rng, jo_range)
        number = _generate_number(freq, strategy, rng)
        games.append(
            PensionRecommendationGame(
                run_id=run_id,
                game_label=_LABELS[label_idx],
                strategy=strategy,
                jo=jo,
                number=number,
            )
        )
        label_idx += 1

    return games
