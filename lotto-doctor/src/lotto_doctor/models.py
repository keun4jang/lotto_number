"""Data models for Lotto Doctor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Draw:
    """A single lotto draw result."""

    draw_no: int
    draw_date: date
    numbers: list[int]  # 6 main numbers, sorted
    bonus: int
    total_sales: int = 0
    first_winners: int = 0
    first_amount: int = 0

    @property
    def n1(self) -> int:
        return self.numbers[0]

    @property
    def n2(self) -> int:
        return self.numbers[1]

    @property
    def n3(self) -> int:
        return self.numbers[2]

    @property
    def n4(self) -> int:
        return self.numbers[3]

    @property
    def n5(self) -> int:
        return self.numbers[4]

    @property
    def n6(self) -> int:
        return self.numbers[5]


@dataclass
class RecommendationRun:
    """A single recommendation run (session)."""

    draw_no: int
    model_name: str
    model_version: str
    seed: int
    created_at: datetime = field(default_factory=datetime.now)
    id: Optional[int] = None


@dataclass
class RecommendationGame:
    """A single recommended game (6 numbers)."""

    run_id: int
    game_label: str   # e.g. "A", "B", ... "J"
    strategy: str     # e.g. "balanced", "recent", "gap", ...
    numbers: list[int]  # 6 numbers, sorted
    id: Optional[int] = None

    @property
    def n1(self) -> int:
        return self.numbers[0]

    @property
    def n2(self) -> int:
        return self.numbers[1]

    @property
    def n3(self) -> int:
        return self.numbers[2]

    @property
    def n4(self) -> int:
        return self.numbers[3]

    @property
    def n5(self) -> int:
        return self.numbers[4]

    @property
    def n6(self) -> int:
        return self.numbers[5]


@dataclass
class CandidateNumber:
    """A scored candidate number."""

    run_id: int
    number: int
    score: float
    rank: int
    id: Optional[int] = None


@dataclass
class EvaluationResult:
    """Result of evaluating a recommended game against an actual draw."""

    run_id: int
    game_label: str
    matched_count: int
    rank_label: str     # "1st", "2nd", "3rd", "4th", "5th", "no_prize"
    has_bonus_match: bool
    id: Optional[int] = None


@dataclass
class BacktestRun:
    """Result of a single backtest evaluation (one draw vs recommendations)."""

    draw_no: int
    matched_3: int = 0
    matched_4: int = 0
    matched_5: int = 0
    matched_5b: int = 0   # 5 + bonus
    matched_6: int = 0
    id: Optional[int] = None


@dataclass
class NumberFeatures:
    """Computed features for a single candidate number."""

    number: int
    long_frequency: float       # overall normalised frequency
    recent_20_frequency: float
    recent_50_frequency: float
    recent_100_frequency: float
    gap_score: float            # score based on draws since last appearance
    trend: float                # recent trend direction
    stability: float            # stability correction


@dataclass
class CombinationScore:
    """Score components for a 6-number combination."""

    numbers: tuple[int, ...]
    strategy: str
    long_frequency: float = 0.0
    recent_frequency: float = 0.0
    gap_score: float = 0.0
    pair_score: float = 0.0
    distribution_score: float = 0.0
    anti_crowding: float = 0.0
    diversity: float = 0.0
    total_score: float = 0.0
