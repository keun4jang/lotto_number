"""EV 성과 계측 루프 — "우리 추천 조합이 실제로 비인기였나?"를 매주 측정.

측정 항목 (모두 상금 분할 노출에 관한 것이며 당첨 확률과 무관):

1. measure_draw_popularity — 실제 당첨 조합의 관측/기대 1등 당첨자 비율
   (crowd_calibration 과 동일한 정의). ratio > 1 이면 그 조합이 실제
   구매자들에게 과선택된 것.
2. evaluate_recommendation_ev — 추천 포트폴리오의 모델 비인기 점수를
   균등 무작위 유효 조합 모집단(시드 고정 10,000개)과 비교한 백분위.
   백분위가 높을수록 "무작위 구매보다 비인기 쪽" 이라는 뜻일 뿐이다.
3. ev_track_record — 회차별 계측치를 ev_metrics 테이블에 누적 (멱등).
4. check_calibration_drift — 모델↔실측 Spearman 상관을 전체 vs 최근
   200회차로 재계산해 모델이 역방향으로 틀어졌는지(음수) 감시만 한다.

통계 기반 추천, EV 관점 비인기 조합 회피, 당첨 보장 없음.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterable, Sequence

from .crowd_calibration import (
    build_calibration_dataset,
    expected_first_winners,
    model_measurement_correlation,
)
from .models import Draw
from .popularity import unpopularity_score

#: 무작위 모집단 크기 및 시드 (결정적 캐시)
POPULATION_SIZE = 10_000
POPULATION_SEED = 20260722

#: 드리프트 점검에 쓰는 최근 회차 수
DRIFT_TRAILING_DRAWS = 200


# ---------------------------------------------------------------------------
# 1. 당첨 조합의 실측 인기 비율
# ---------------------------------------------------------------------------


def measure_draw_popularity(
    draw: Draw, total_sales: int | None = None
) -> float | None:
    """당첨 조합의 관측/기대 1등 당첨자 비율. 측정 불가 시 None.

    ratio > 1: 실제 구매자들이 이 조합(류)을 과선택. ratio < 1: 과소선택.
    당첨자 수/판매액이 없거나 기대 당첨자 수가 0이면 None.
    """
    sales = total_sales if total_sales is not None else draw.total_sales
    if sales is None or sales <= 0:
        return None
    if draw.first_winners is None:
        return None
    exp = expected_first_winners(sales)
    if exp <= 0:
        return None
    return float(draw.first_winners) / exp


# ---------------------------------------------------------------------------
# 2. 포트폴리오 비인기 백분위
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def random_population_scores(
    n: int = POPULATION_SIZE, seed: int = POPULATION_SEED
) -> tuple[float, ...]:
    """균등 무작위 유효 조합 n개의 unpopularity_score (시드 고정, 캐시)."""
    rng = random.Random(seed)
    scores = []
    for _ in range(n):
        combo = sorted(rng.sample(range(1, 46), 6))
        scores.append(unpopularity_score(combo))
    return tuple(scores)


def _percentile_of(value: float, population: Sequence[float]) -> float:
    """population 대비 value 의 백분위 [0,100] (mid-rank)."""
    if not population:
        return 0.0
    below = sum(1 for s in population if s < value)
    equal = sum(1 for s in population if s == value)
    return 100.0 * (below + 0.5 * equal) / len(population)


def evaluate_recommendation_ev(
    games: Sequence[Any],
    winning_numbers: Sequence[int] | None = None,
    prev_numbers: Sequence[int] | None = None,
    population: Sequence[float] | None = None,
) -> dict[str, Any]:
    """추천 게임들의 모델 비인기 점수와 무작위 대비 백분위.

    games: .numbers 속성이 있는 객체 또는 번호 리스트의 시퀀스.
    반환 dict:
      game_scores, portfolio_mean_score, population_mean_score,
      portfolio_percentile (무작위 구매 대비), winning_combo_score (있으면).
    당첨 확률과 무관 — 상금 분할 노출 측정만.
    """
    pop = tuple(population) if population is not None else random_population_scores()
    prev = list(prev_numbers) if prev_numbers else None

    game_scores: list[float] = []
    for g in games:
        nums = list(getattr(g, "numbers", g))
        game_scores.append(unpopularity_score(nums, prev))

    portfolio_mean = sum(game_scores) / len(game_scores) if game_scores else 0.0
    result: dict[str, Any] = {
        "game_scores": game_scores,
        "portfolio_mean_score": portfolio_mean,
        "population_mean_score": sum(pop) / len(pop) if pop else 0.0,
        "portfolio_percentile": _percentile_of(portfolio_mean, pop),
        "winning_combo_score": None,
    }
    if winning_numbers is not None:
        result["winning_combo_score"] = unpopularity_score(list(winning_numbers), prev)
    return result


# ---------------------------------------------------------------------------
# 3. ev_metrics 테이블 (누적 트랙 레코드)
# ---------------------------------------------------------------------------

_EV_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ev_metrics (
    draw_no              INTEGER PRIMARY KEY,
    portfolio_mean_score REAL NOT NULL,
    portfolio_percentile REAL NOT NULL,
    winning_combo_score  REAL,
    winner_ratio         REAL,
    created_at           TEXT NOT NULL
);
"""


def ensure_ev_table(conn: sqlite3.Connection) -> None:
    """멱등: ev_metrics 테이블 생성 (database._migrate 스타일)."""
    conn.executescript(_EV_SCHEMA_SQL)


def upsert_ev_metric(
    conn: sqlite3.Connection,
    draw_no: int,
    portfolio_mean_score: float,
    portfolio_percentile: float,
    winning_combo_score: float | None,
    winner_ratio: float | None,
    created_at: str | None = None,
) -> None:
    """같은 draw_no 재실행 시 대체 (멱등)."""
    ensure_ev_table(conn)
    ts = created_at or datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO ev_metrics
          (draw_no, portfolio_mean_score, portfolio_percentile,
           winning_combo_score, winner_ratio, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (draw_no, portfolio_mean_score, portfolio_percentile,
         winning_combo_score, winner_ratio, ts),
    )


def ev_track_record(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """누적 EV 계측 이력 (draw_no 오름차순)."""
    ensure_ev_table(conn)
    rows = conn.execute(
        "SELECT * FROM ev_metrics ORDER BY draw_no"
    ).fetchall()
    return [dict(r) if isinstance(r, sqlite3.Row) else
            dict(zip(["draw_no", "portfolio_mean_score", "portfolio_percentile",
                      "winning_combo_score", "winner_ratio", "created_at"], r))
            for r in rows]


# ---------------------------------------------------------------------------
# 4. 보정 드리프트 점검
# ---------------------------------------------------------------------------


def check_calibration_drift(
    draws: Iterable[Draw],
    trailing: int = DRIFT_TRAILING_DRAWS,
) -> dict[str, Any]:
    """모델↔실측 Spearman 상관: 전체 vs 최근 trailing 회차.

    trailing 상관이 음수면 모델이 최근 데이터에서 역방향 → 재보정 권고.
    모델을 자동으로 바꾸지는 않는다 (감시만).
    """
    rows = build_calibration_dataset(draws)
    if len(rows) < 10:
        return {"full_spearman": None, "trailing_spearman": None,
                "drift_warning": False, "n_full": len(rows), "n_trailing": 0}
    _, full_sp = model_measurement_correlation(rows)
    tail = rows[-trailing:]
    _, tail_sp = model_measurement_correlation(tail)
    return {
        "full_spearman": full_sp,
        "trailing_spearman": tail_sp,
        "drift_warning": tail_sp < 0.0,
        "n_full": len(rows),
        "n_trailing": len(tail),
    }


# ---------------------------------------------------------------------------
# 5. 반성 리포트용 텍스트 섹션
# ---------------------------------------------------------------------------


def format_ev_section(
    ev: dict[str, Any],
    winner_ratio: float | None,
    history: Sequence[dict[str, Any]],
    drift: dict[str, Any] | None = None,
) -> str:
    """반성 텔레그램에 붙일 '📈 EV 계측' 섹션 (6줄 이내, 확률 주장 없음)."""
    lines = ["\n━━━━━━━━━━━━━━━━━━━━", "📈 EV 계측 (상금 분할 노출, 당첨 확률과 무관)\n"]
    pct = ev["portfolio_percentile"]
    lines.append(f"  이번 주 포트폴리오 비인기 백분위: 상위 {100 - pct:.0f}% (무작위 구매 대비 {pct:.0f}백분위)")
    if winner_ratio is not None:
        tag = "과선택" if winner_ratio > 1 else "과소선택"
        lines.append(f"  당첨 조합 실측 인기 비율: {winner_ratio:.2f}배 ({tag})")
    if history:
        avg = sum(h["portfolio_percentile"] for h in history) / len(history)
        lines.append(f"  누적 평균 백분위: {avg:.0f} ({len(history)}주 추적)")
    if drift and drift.get("drift_warning"):
        lines.append(
            f"  ⚠️ 최근 {drift['n_trailing']}회차 모델-실측 상관 음수"
            f" ({drift['trailing_spearman']:.2f}) → 재보정 검토 필요"
        )
    return "\n".join(lines)
