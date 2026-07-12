"""SQLite database operations for Pension Lottery 720+."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .pension_models import (
    PensionDraw,
    PensionEvaluationResult,
    PensionRecommendationGame,
    PensionRecommendationRun,
)

_PENSION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pension_draws (
    draw_no     INTEGER PRIMARY KEY,
    draw_date   TEXT NOT NULL,
    jo          INTEGER NOT NULL,
    number      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pension_recommendation_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_no         INTEGER NOT NULL,
    model_version   TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pension_recommendation_games (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES pension_recommendation_runs(id),
    game_label  TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    jo          INTEGER NOT NULL,
    number      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pension_evaluation_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES pension_recommendation_runs(id),
    game_label      TEXT NOT NULL,
    jo_match        INTEGER NOT NULL,
    matched_suffix  INTEGER NOT NULL,
    prize_rank      TEXT NOT NULL
);
"""


def init_pension_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_PENSION_SCHEMA_SQL)
        conn.commit()


def upsert_pension_draw(conn: sqlite3.Connection, draw: PensionDraw) -> None:
    conn.execute(
        """INSERT INTO pension_draws (draw_no, draw_date, jo, number)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(draw_no) DO UPDATE SET
               draw_date=excluded.draw_date,
               jo=excluded.jo,
               number=excluded.number""",
        (draw.draw_no, str(draw.draw_date), draw.jo, draw.number),
    )


def get_all_pension_draws(conn: sqlite3.Connection) -> list[PensionDraw]:
    rows = conn.execute(
        "SELECT draw_no, draw_date, jo, number FROM pension_draws ORDER BY draw_no"
    ).fetchall()
    result = []
    for draw_no, draw_date, jo, number in rows:
        d = date.fromisoformat(draw_date) if draw_date else date.today()
        result.append(PensionDraw(draw_no=draw_no, draw_date=d, jo=jo, number=number))
    return result


def get_latest_pension_draw_no(conn: sqlite3.Connection) -> Optional[int]:
    row = conn.execute("SELECT MAX(draw_no) FROM pension_draws").fetchone()
    return row[0] if row and row[0] is not None else None


def get_pension_draw(conn: sqlite3.Connection, draw_no: int) -> Optional[PensionDraw]:
    row = conn.execute(
        "SELECT draw_no, draw_date, jo, number FROM pension_draws WHERE draw_no=?",
        (draw_no,),
    ).fetchone()
    if not row:
        return None
    d = date.fromisoformat(row[1]) if row[1] else date.today()
    return PensionDraw(draw_no=row[0], draw_date=d, jo=row[2], number=row[3])


def insert_pension_run(conn: sqlite3.Connection, run: PensionRecommendationRun) -> int:
    cur = conn.execute(
        """INSERT INTO pension_recommendation_runs (draw_no, model_version, seed, created_at)
           VALUES (?, ?, ?, ?)""",
        (run.draw_no, run.model_version, run.seed, run.created_at.isoformat()),
    )
    return cur.lastrowid


def get_latest_pension_run(conn: sqlite3.Connection) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, draw_no, model_version FROM pension_recommendation_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "draw_no": row[1], "model_version": row[2]}


def insert_pension_game(conn: sqlite3.Connection, game: PensionRecommendationGame) -> None:
    conn.execute(
        """INSERT INTO pension_recommendation_games (run_id, game_label, strategy, jo, number)
           VALUES (?, ?, ?, ?, ?)""",
        (game.run_id, game.game_label, game.strategy, game.jo, game.number),
    )


def get_pension_games_for_run(conn: sqlite3.Connection, run_id: int) -> list[PensionRecommendationGame]:
    rows = conn.execute(
        "SELECT run_id, game_label, strategy, jo, number, id FROM pension_recommendation_games WHERE run_id=? ORDER BY game_label",
        (run_id,),
    ).fetchall()
    return [
        PensionRecommendationGame(
            run_id=r[0], game_label=r[1], strategy=r[2], jo=r[3], number=r[4], id=r[5]
        )
        for r in rows
    ]


def insert_pension_evaluation(conn: sqlite3.Connection, result: PensionEvaluationResult) -> None:
    conn.execute(
        """INSERT INTO pension_evaluation_results (run_id, game_label, jo_match, matched_suffix, prize_rank)
           VALUES (?, ?, ?, ?, ?)""",
        (result.run_id, result.game_label, int(result.jo_match), result.matched_suffix, result.prize_rank),
    )
