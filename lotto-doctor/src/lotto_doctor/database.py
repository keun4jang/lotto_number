"""SQLite database operations for Lotto Doctor."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from .models import (
    BacktestRun,
    CandidateNumber,
    Draw,
    EvaluationResult,
    RecommendationGame,
    RecommendationRun,
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS draws (
    draw_no         INTEGER PRIMARY KEY,
    draw_date       TEXT NOT NULL,
    n1              INTEGER NOT NULL,
    n2              INTEGER NOT NULL,
    n3              INTEGER NOT NULL,
    n4              INTEGER NOT NULL,
    n5              INTEGER NOT NULL,
    n6              INTEGER NOT NULL,
    bonus           INTEGER NOT NULL,
    total_sales     INTEGER DEFAULT 0,
    first_winners   INTEGER DEFAULT 0,
    first_amount    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recommendation_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_no         INTEGER NOT NULL,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_games (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES recommendation_runs(id),
    game_label  TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    n1          INTEGER NOT NULL,
    n2          INTEGER NOT NULL,
    n3          INTEGER NOT NULL,
    n4          INTEGER NOT NULL,
    n5          INTEGER NOT NULL,
    n6          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_numbers (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  INTEGER NOT NULL REFERENCES recommendation_runs(id),
    number  INTEGER NOT NULL,
    score   REAL NOT NULL,
    rank    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES recommendation_runs(id),
    game_label          TEXT NOT NULL,
    matched_count       INTEGER NOT NULL,
    rank_label          TEXT NOT NULL,
    has_bonus_match     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_no     INTEGER NOT NULL,
    matched_3   INTEGER DEFAULT 0,
    matched_4   INTEGER DEFAULT 0,
    matched_5   INTEGER DEFAULT 0,
    matched_5b  INTEGER DEFAULT 0,
    matched_6   INTEGER DEFAULT 0
);
"""

# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row factory."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent schema migrations — safe to run multiple times."""
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(recommendation_runs)").fetchall()
    }
    migrations = [
        ("config_hash",      "ALTER TABLE recommendation_runs ADD COLUMN config_hash TEXT"),
        ("game_count",       "ALTER TABLE recommendation_runs ADD COLUMN game_count INTEGER"),
        ("strategy_summary", "ALTER TABLE recommendation_runs ADD COLUMN strategy_summary TEXT"),
        ("code_commit",      "ALTER TABLE recommendation_runs ADD COLUMN code_commit TEXT"),
    ]
    for col, sql in migrations:
        if col not in existing:
            conn.execute(sql)

    # Indexes (idempotent via IF NOT EXISTS)
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_runs_draw_no
            ON recommendation_runs(draw_no);
        CREATE INDEX IF NOT EXISTS idx_runs_config_hash
            ON recommendation_runs(config_hash);
    """)
    conn.commit()


def init_db(db_path: Path) -> None:
    """Create tables if they do not exist, then apply migrations."""
    with get_connection(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        _migrate(conn)


# ---------------------------------------------------------------------------
# Draws
# ---------------------------------------------------------------------------


def upsert_draw(conn: sqlite3.Connection, draw: Draw) -> None:
    """Insert or replace a draw record."""
    conn.execute(
        """
        INSERT OR REPLACE INTO draws
          (draw_no, draw_date, n1, n2, n3, n4, n5, n6, bonus,
           total_sales, first_winners, first_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draw.draw_no,
            draw.draw_date.isoformat(),
            draw.n1, draw.n2, draw.n3, draw.n4, draw.n5, draw.n6,
            draw.bonus,
            draw.total_sales,
            draw.first_winners,
            draw.first_amount,
        ),
    )


def get_all_draws(conn: sqlite3.Connection) -> list[Draw]:
    """Return all draws ordered by draw_no."""
    rows = conn.execute(
        "SELECT * FROM draws ORDER BY draw_no"
    ).fetchall()
    return [_row_to_draw(r) for r in rows]


def get_draw(conn: sqlite3.Connection, draw_no: int) -> Optional[Draw]:
    """Return a single draw or None."""
    row = conn.execute(
        "SELECT * FROM draws WHERE draw_no = ?", (draw_no,)
    ).fetchone()
    return _row_to_draw(row) if row else None


def get_latest_draw_no(conn: sqlite3.Connection) -> Optional[int]:
    """Return the highest draw_no in the DB, or None if empty."""
    row = conn.execute("SELECT MAX(draw_no) AS mx FROM draws").fetchone()
    return row["mx"] if row and row["mx"] is not None else None


def _row_to_draw(row: sqlite3.Row) -> Draw:
    return Draw(
        draw_no=row["draw_no"],
        draw_date=date.fromisoformat(row["draw_date"]),
        numbers=[row["n1"], row["n2"], row["n3"], row["n4"], row["n5"], row["n6"]],
        bonus=row["bonus"],
        total_sales=row["total_sales"],
        first_winners=row["first_winners"],
        first_amount=row["first_amount"],
    )


# ---------------------------------------------------------------------------
# Recommendation runs
# ---------------------------------------------------------------------------


def insert_recommendation_run(
    conn: sqlite3.Connection, run: RecommendationRun
) -> int:
    """Insert a recommendation run and return its ID."""
    cur = conn.execute(
        """
        INSERT INTO recommendation_runs
          (draw_no, model_name, model_version, seed, created_at,
           config_hash, game_count, strategy_summary, code_commit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.draw_no,
            run.model_name,
            run.model_version,
            run.seed,
            run.created_at.isoformat(),
            run.config_hash,
            run.game_count,
            run.strategy_summary,
            run.code_commit,
        ),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_valid_recommendation(
    conn: sqlite3.Connection,
    draw_no: int,
    model_version: str,
    config_hash: str,
    expected_game_count: int,
) -> Optional[dict[str, Any]]:
    """캐시 강화 조회: model_version/config_hash/game_count 모두 일치하는 run만 반환."""
    row = conn.execute(
        """
        SELECT r.id, r.draw_no, r.model_version, r.game_count
        FROM recommendation_runs r
        WHERE r.draw_no = ?
          AND r.model_version = ?
          AND r.config_hash = ?
          AND r.game_count = ?
          AND (SELECT COUNT(*) FROM recommendation_games g WHERE g.run_id = r.id) = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (draw_no, model_version, config_hash, expected_game_count, expected_game_count),
    ).fetchone()
    return dict(row) if row else None


def get_recommendation_runs_for_draw(
    conn: sqlite3.Connection, draw_no: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM recommendation_runs WHERE draw_no = ? ORDER BY created_at DESC",
        (draw_no,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_recommendation_run(
    conn: sqlite3.Connection,
) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM recommendation_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Recommendation games
# ---------------------------------------------------------------------------


def insert_recommendation_game(
    conn: sqlite3.Connection, game: RecommendationGame
) -> int:
    cur = conn.execute(
        """
        INSERT INTO recommendation_games (run_id, game_label, strategy, n1, n2, n3, n4, n5, n6)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game.run_id,
            game.game_label,
            game.strategy,
            game.n1, game.n2, game.n3, game.n4, game.n5, game.n6,
        ),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_games_for_run(
    conn: sqlite3.Connection, run_id: int
) -> list[RecommendationGame]:
    rows = conn.execute(
        "SELECT * FROM recommendation_games WHERE run_id = ? ORDER BY game_label",
        (run_id,),
    ).fetchall()
    return [
        RecommendationGame(
            run_id=r["run_id"],
            game_label=r["game_label"],
            strategy=r["strategy"],
            numbers=[r["n1"], r["n2"], r["n3"], r["n4"], r["n5"], r["n6"]],
            id=r["id"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Candidate numbers
# ---------------------------------------------------------------------------


def insert_candidate_numbers(
    conn: sqlite3.Connection, candidates: list[CandidateNumber]
) -> None:
    conn.executemany(
        "INSERT INTO candidate_numbers (run_id, number, score, rank) VALUES (?, ?, ?, ?)",
        [(c.run_id, c.number, c.score, c.rank) for c in candidates],
    )


def get_candidate_numbers(
    conn: sqlite3.Connection, run_id: int
) -> list[CandidateNumber]:
    rows = conn.execute(
        "SELECT * FROM candidate_numbers WHERE run_id = ? ORDER BY rank",
        (run_id,),
    ).fetchall()
    return [
        CandidateNumber(
            run_id=r["run_id"],
            number=r["number"],
            score=r["score"],
            rank=r["rank"],
            id=r["id"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Evaluation results
# ---------------------------------------------------------------------------


def insert_evaluation_result(
    conn: sqlite3.Connection, result: EvaluationResult
) -> int:
    cur = conn.execute(
        """
        INSERT INTO evaluation_results (run_id, game_label, matched_count, rank_label, has_bonus_match)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            result.run_id,
            result.game_label,
            result.matched_count,
            result.rank_label,
            int(result.has_bonus_match),
        ),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_evaluation_results(
    conn: sqlite3.Connection, run_id: int
) -> list[EvaluationResult]:
    rows = conn.execute(
        "SELECT * FROM evaluation_results WHERE run_id = ? ORDER BY game_label",
        (run_id,),
    ).fetchall()
    return [
        EvaluationResult(
            run_id=r["run_id"],
            game_label=r["game_label"],
            matched_count=r["matched_count"],
            rank_label=r["rank_label"],
            has_bonus_match=bool(r["has_bonus_match"]),
            id=r["id"],
        )
        for r in rows
    ]


def get_all_evaluation_results(
    conn: sqlite3.Connection,
) -> list[EvaluationResult]:
    rows = conn.execute(
        "SELECT * FROM evaluation_results ORDER BY run_id, game_label"
    ).fetchall()
    return [
        EvaluationResult(
            run_id=r["run_id"],
            game_label=r["game_label"],
            matched_count=r["matched_count"],
            rank_label=r["rank_label"],
            has_bonus_match=bool(r["has_bonus_match"]),
            id=r["id"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Backtest runs
# ---------------------------------------------------------------------------


def insert_backtest_run(conn: sqlite3.Connection, run: BacktestRun) -> int:
    cur = conn.execute(
        """
        INSERT INTO backtest_runs (draw_no, matched_3, matched_4, matched_5, matched_5b, matched_6)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run.draw_no, run.matched_3, run.matched_4, run.matched_5, run.matched_5b, run.matched_6),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_all_backtest_runs(conn: sqlite3.Connection) -> list[BacktestRun]:
    rows = conn.execute(
        "SELECT * FROM backtest_runs ORDER BY draw_no"
    ).fetchall()
    return [
        BacktestRun(
            draw_no=r["draw_no"],
            matched_3=r["matched_3"],
            matched_4=r["matched_4"],
            matched_5=r["matched_5"],
            matched_5b=r["matched_5b"],
            matched_6=r["matched_6"],
            id=r["id"],
        )
        for r in rows
    ]
