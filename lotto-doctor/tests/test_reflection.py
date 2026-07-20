"""Tests for reflection weight-adjustment math and version bumping."""

from __future__ import annotations

import sqlite3

import pytest
import yaml

from lotto_doctor.reflection import (
    _bump_patch_version,
    apply_strategy_adjustment,
    compute_weight_adjustment,
    load_strategy_performance,
)


def _perf_entry(total_games: int, avg_match: float, match_4: int = 0, match_5: int = 0) -> dict:
    return {
        "total_games": total_games,
        "match_3": 0,
        "match_4": match_4,
        "match_5": match_5,
        "match_5b": 0,
        "match_6": 0,
        "avg_match": avg_match,
        "total_match_sum": int(avg_match * total_games),
    }


def _cfg(strategy_games: dict[str, int]) -> dict:
    return {
        "generator": {"strategy_games": dict(strategy_games)},
        "reflection": {
            "min_samples": 30,
            "shrinkage_k": 20,
            "max_adjustment": 0.05,
            "rare_event_cap": 2,
        },
    }


def test_adjustment_preserves_total_game_count():
    cfg = _cfg({"a": 3, "b": 3, "c": 2, "d": 2})
    perf = {
        "a": _perf_entry(100, 0.9),
        "b": _perf_entry(100, 0.7),
        "c": _perf_entry(100, 0.8),
        "d": _perf_entry(100, 0.8),
    }
    new = compute_weight_adjustment(perf, cfg)
    assert new is not None
    assert sum(new.values()) == 10
    assert all(isinstance(v, int) and v >= 0 for v in new.values())


def test_equal_performance_does_not_skew_allocation():
    """Regression: 반올림 잔여분이 마지막 전략에 몰려 2,2,2,4처럼 왜곡되면 안 된다."""
    cfg = _cfg({"a": 3, "b": 3, "c": 2, "d": 2})
    perf = {s: _perf_entry(200, 0.8) for s in ["a", "b", "c", "d"]}
    new = compute_weight_adjustment(perf, cfg)
    assert new is not None
    assert sum(new.values()) == 10
    # 동일 성과 + 대칭 기본배분 → 어떤 전략도 잔여분을 독식하지 않는다
    assert max(new.values()) - min(new.values()) <= 1


def test_zero_game_strategy_does_not_crash_and_stays_zero():
    """Regression: strategy_games에 0게임 전략이 있으면 KeyError가 났었다."""
    cfg = _cfg({"a": 4, "b": 3, "c": 3, "dead": 0})
    perf = {
        "a": _perf_entry(100, 0.9),
        "b": _perf_entry(100, 0.8),
        "c": _perf_entry(100, 0.7),
    }
    new = compute_weight_adjustment(perf, cfg)
    assert new is not None
    assert new["dead"] == 0
    assert sum(new.values()) == 10


def test_insufficient_data_returns_none():
    cfg = _cfg({"a": 5, "b": 5})
    perf = {"a": _perf_entry(5, 0.9), "b": _perf_entry(5, 0.7)}  # < min_samples
    assert compute_weight_adjustment(perf, cfg) is None


def test_missing_strategy_data_keeps_base_allocation():
    """데이터가 부족한 활성 전략은 (reliability=0이므로) 기본 배분을 유지한다."""
    cfg = _cfg({"a": 4, "b": 4, "c": 2})
    perf = {
        "a": _perf_entry(100, 0.9),
        "b": _perf_entry(100, 0.9),
        # "c"는 데이터 없음
    }
    new = compute_weight_adjustment(perf, cfg)
    assert new is not None
    assert sum(new.values()) == 10
    # c는 기본배분 2에서 크게 벗어나지 않아야 함 (delta=0 → quota 그대로)
    assert new["c"] == 2


@pytest.mark.parametrize(
    "current,expected",
    [
        ("be-v1.1.0-ev", "be-v1.1.1-ev"),
        ("be-v1.0.0", "be-v1.0.1"),
        ("be-v2.3.9", "be-v2.3.10"),
        ("pension-v1.0.0", "pension-v1.0.0"),  # 형식 불일치 → 그대로
        ("garbage", "garbage"),
    ],
)
def test_bump_patch_version(current, expected):
    assert _bump_patch_version(current) == expected


_YAML_TEMPLATE = """\
app:
  model_version: "be-v1.1.0-ev"

generator:
  strategy_games:
    balanced: 1
    recent: 1
    gap: 1

scoring:
  weights:
    balanced:
      long_frequency: 0.5
    recent:
      recent_frequency: 0.5
"""


def test_apply_strategy_adjustment_updates_yaml_and_bumps_version(tmp_path):
    cfg_path = tmp_path / "default.yaml"
    cfg_path.write_text(_YAML_TEMPLATE, encoding="utf-8")

    new_ver = apply_strategy_adjustment(
        {"balanced": 2, "recent": 0, "gap": 1}, config_path=str(cfg_path)
    )
    assert new_ver == "be-v1.1.1-ev"

    loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert loaded["generator"]["strategy_games"] == {"balanced": 2, "recent": 0, "gap": 1}
    # scoring 섹션의 동명 키는 건드리지 않아야 한다
    assert loaded["scoring"]["weights"]["balanced"]["long_frequency"] == 0.5
    assert loaded["app"]["model_version"] == "be-v1.1.1-ev"


def test_apply_strategy_adjustment_no_change_no_bump(tmp_path):
    cfg_path = tmp_path / "default.yaml"
    cfg_path.write_text(_YAML_TEMPLATE, encoding="utf-8")

    new_ver = apply_strategy_adjustment(
        {"balanced": 1, "recent": 1, "gap": 1}, config_path=str(cfg_path)
    )
    assert new_ver == ""  # 변경 없음 → 버전 유지
    loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert loaded["app"]["model_version"] == "be-v1.1.0-ev"


def test_load_strategy_performance_classifies_ranks(tmp_path):
    db_path = tmp_path / "perf.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE recommendation_games (run_id INTEGER, game_label TEXT, strategy TEXT)")
    conn.execute(
        "CREATE TABLE evaluation_results (run_id INTEGER, game_label TEXT, matched_count INTEGER, rank_label TEXT)"
    )
    rows = [
        (1, "A", "balanced", 5, "2nd"),   # 5+bonus
        (1, "B", "balanced", 5, "3rd"),   # 5
        (1, "C", "balanced", 3, "5th"),   # 3
    ]
    for run_id, label, strategy, matched, rank in rows:
        conn.execute("INSERT INTO recommendation_games VALUES (?,?,?)", (run_id, label, strategy))
        conn.execute("INSERT INTO evaluation_results VALUES (?,?,?,?)", (run_id, label, matched, rank))
    conn.commit()
    conn.close()

    perf = load_strategy_performance(str(db_path))
    p = perf["balanced"]
    assert p["total_games"] == 3
    assert p["match_5b"] == 1
    assert p["match_5"] == 1
    assert p["match_3"] == 1
    assert p["avg_match"] == pytest.approx(13 / 3)
