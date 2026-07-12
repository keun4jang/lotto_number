"""Data models for Pension Lottery 720+ (연금복권720+)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class PensionDraw:
    """A single pension lottery draw result."""

    draw_no: int
    draw_date: date
    jo: int          # 조 (1~5)
    number: str      # 6-digit string, e.g. "123456"

    @property
    def digits(self) -> list[int]:
        return [int(d) for d in self.number.zfill(6)]


@dataclass
class PensionRecommendationRun:
    """A single pension recommendation run."""

    draw_no: int
    model_version: str
    seed: int
    created_at: datetime = field(default_factory=datetime.now)
    id: Optional[int] = None


@dataclass
class PensionRecommendationGame:
    """A single recommended pension lottery game."""

    run_id: int
    game_label: str   # "A", "B", "C", ...
    strategy: str
    jo: int           # 조 (1~5)
    number: str       # 6-digit string
    id: Optional[int] = None

    @property
    def digits(self) -> list[int]:
        return [int(d) for d in self.number.zfill(6)]


@dataclass
class PensionEvaluationResult:
    """Result of evaluating a pension recommendation against actual draw."""

    run_id: int
    game_label: str
    jo_match: bool
    matched_suffix: int   # how many trailing digits match (0~6)
    prize_rank: str       # "1st","2nd","3rd","4th","5th","6th","7th","no_prize"
    id: Optional[int] = None
