"""Tests for database schema migration and recommendation cache lookup."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from lotto_doctor.database import (
    get_connection,
    get_valid_recommendation,
    init_db,
    insert_recommendation_game,
    insert_recommendation_run,
)
from lotto_doctor.models import RecommendationGame, RecommendationRun


def test_cli_module_imports():
    """Regression: database.get_valid_recommendation 누락으로 CLI 전체가 ImportError였다."""
    import lotto_doctor.cli  # noqa: F401


def test_init_db_migrates_old_schema(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE recommendation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draw_no INTEGER NOT NULL,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            seed INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    init_db(db)  # 마이그레이션 적용
    init_db(db)  # 멱등성 확인

    conn = get_connection(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(recommendation_runs)")}
    conn.close()
    assert {"config_hash", "game_count", "strategy_summary", "code_commit"} <= cols


def _make_run(draw_no: int, version: str, cfg_hash: str, game_count: int) -> RecommendationRun:
    return RecommendationRun(
        draw_no=draw_no,
        model_name="balanced-ensemble",
        model_version=version,
        seed=draw_no,
        created_at=datetime(2026, 1, 1),
        config_hash=cfg_hash,
        game_count=game_count,
        strategy_summary="balanced:1,recent:1",
        code_commit="abc1234",
    )


def test_get_valid_recommendation_cache(tmp_path):
    db = tmp_path / "cache.db"
    init_db(db)

    conn = get_connection(db)
    run_id = insert_recommendation_run(conn, _make_run(1200, "v1", "hash-a", 2))

    # 게임 레코드 수가 game_count와 다르면 캐시 미스여야 한다
    assert get_valid_recommendation(conn, 1200, "v1", "hash-a", 2) is None

    insert_recommendation_game(
        conn, RecommendationGame(run_id=run_id, game_label="A", strategy="balanced",
                                 numbers=[1, 5, 12, 23, 34, 45])
    )
    insert_recommendation_game(
        conn, RecommendationGame(run_id=run_id, game_label="B", strategy="recent",
                                 numbers=[2, 8, 17, 28, 33, 41])
    )
    conn.commit()

    hit = get_valid_recommendation(conn, 1200, "v1", "hash-a", 2)
    assert hit is not None
    assert hit["id"] == run_id

    # 어떤 조건이든 하나라도 어긋나면 캐시 미스
    assert get_valid_recommendation(conn, 1200, "v2", "hash-a", 2) is None
    assert get_valid_recommendation(conn, 1200, "v1", "hash-b", 2) is None
    assert get_valid_recommendation(conn, 1200, "v1", "hash-a", 3) is None
    assert get_valid_recommendation(conn, 1201, "v1", "hash-a", 2) is None
    conn.close()
