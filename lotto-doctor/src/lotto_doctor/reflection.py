"""자동 반성 및 피드백 시스템 - 매주 일요일 실행."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_strategy_performance(db_path: str) -> dict[str, dict]:
    """DB에서 전략별 누적 적중 성과를 집계."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("""
            SELECT rg.strategy, er.matched_count, er.rank_label, COUNT(*) as cnt
            FROM recommendation_games rg
            JOIN evaluation_results er ON rg.run_id = er.run_id AND rg.game_label = er.game_label
            GROUP BY rg.strategy, er.matched_count, er.rank_label
        """).fetchall()
    except Exception:
        return {}
    finally:
        conn.close()

    perf: dict[str, dict] = defaultdict(lambda: {
        "total_games": 0,
        "match_3": 0, "match_4": 0, "match_5": 0, "match_5b": 0, "match_6": 0,
        "avg_match": 0.0, "total_match_sum": 0,
    })

    for strategy, matched, rank, cnt in rows:
        p = perf[strategy]
        p["total_games"] += cnt
        p["total_match_sum"] += matched * cnt
        if matched == 3:
            p["match_3"] += cnt
        elif matched == 4:
            p["match_4"] += cnt
        elif matched == 5 and rank == "3rd":
            p["match_5"] += cnt
        elif matched == 5 and rank == "2nd":
            p["match_5b"] += cnt
        elif matched == 6:
            p["match_6"] += cnt

    for p in perf.values():
        if p["total_games"] > 0:
            p["avg_match"] = p["total_match_sum"] / p["total_games"]

    return dict(perf)


def compute_weight_adjustment(
    perf: dict[str, dict],
    cfg: dict[str, Any],
    min_games: int = 20,
    adjust_rate: float = 0.05,
) -> dict[str, float] | None:
    """전략별 평균 적중수 기반으로 strategy_games 비율 소폭 조정.

    데이터가 충분할 때만 조정. 변화량은 ±5% 이내로 제한.
    Returns None if not enough data.
    """
    valid = {s: p for s, p in perf.items() if p["total_games"] >= min_games}
    if len(valid) < 3:
        return None  # 데이터 부족

    avg_scores = {s: p["avg_match"] for s, p in valid.items()}
    total_score = sum(avg_scores.values())
    if total_score == 0:
        return None

    current_games: dict[str, int] = cfg["generator"]["strategy_games"]
    total_current = sum(current_games.values())  # 10

    new_ratios = {s: avg_scores.get(s, 1.0) / total_score for s in current_games}

    # 현재 비율
    current_ratios = {s: v / total_current for s, v in current_games.items()}

    # 조정: 현재 비율과 성과 비율의 중간값 (급격한 변화 방지)
    adjusted = {}
    for s in current_games:
        target = new_ratios.get(s, current_ratios[s])
        current = current_ratios[s]
        # 최대 adjust_rate만큼만 이동
        delta = target - current
        delta = max(-adjust_rate, min(adjust_rate, delta))
        adjusted[s] = current + delta

    # 정규화 후 게임 수로 변환 (합계 10)
    total_adj = sum(adjusted.values())
    new_games = {}
    remainder = total_current
    sorted_strategies = sorted(adjusted.items(), key=lambda x: x[1], reverse=True)
    for i, (s, ratio) in enumerate(sorted_strategies):
        if i == len(sorted_strategies) - 1:
            new_games[s] = max(1, remainder)
        else:
            g = max(1, round(ratio / total_adj * total_current))
            new_games[s] = g
            remainder -= g

    return new_games


def generate_reflection_text(
    draw_no: int,
    draw_numbers: list[int],
    bonus: int,
    games: list[dict],
    perf: dict[str, dict],
    new_strategy_games: dict[str, float] | None,
) -> str:
    """일요일 반성 텔레그램 메시지 생성."""
    lines = [
        f"📋 제{draw_no}회 결과 반성 리포트\n",
        f"🎱 당첨번호: {' '.join(f'{n:02d}' for n in sorted(draw_numbers))} + 보너스 {bonus:02d}\n",
        "━━━━━━━━━━━━━━━━━━━━",
        "🎯 이번 회 추천 결과\n",
    ]

    best_match = 0
    for g in games:
        matched = g["matched_count"]
        rank = g["rank_label"]
        bonus_mark = "⭐" if g["has_bonus_match"] and matched == 5 else ""
        rank_emoji = {"1st": "🥇", "2nd": "🥈", "3rd": "🥉", "4th": "🎖", "5th": "✅"}.get(rank, "❌")
        lines.append(f"  {g['game_label']}게임 [{g['strategy']}] → {matched}개 {rank_emoji}{bonus_mark}")
        best_match = max(best_match, matched)

    lines.append(f"\n최고 적중: {best_match}개")

    # 전략별 누적 성과
    if perf:
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("📊 전략별 누적 성과\n")
        for strategy, p in sorted(perf.items(), key=lambda x: x[1]["avg_match"], reverse=True):
            if p["total_games"] == 0:
                continue
            lines.append(
                f"  [{strategy}] 평균 {p['avg_match']:.2f}개 "
                f"(총 {p['total_games']}게임 | 3개↑: {p['match_3']+p['match_4']+p['match_5']+p['match_5b']}회)"
            )

    # 시스템 조정 내역
    if new_strategy_games:
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔧 시스템 자동 조정\n")
        lines.append("성과 기반으로 다음 주 전략 배분 조정:")
        for s, g in new_strategy_games.items():
            lines.append(f"  {s}: {g}게임")
    else:
        lines.append("\n🔧 시스템 조정: 데이터 축적 중 (아직 조정 없음)")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ 모든 6개 번호 조합의 1등 확률은 동일합니다.")
    lines.append("이 시스템은 통계 패턴 분석이며 당첨을 보장하지 않습니다.")

    return "\n".join(lines)


def save_reflection_report(
    draw_no: int,
    text: str,
    perf: dict[str, dict],
    new_strategy_games: dict | None,
    reports_dir: str = "reports",
) -> Path:
    """반성 리포트를 Markdown 파일로 저장."""
    out = Path(reports_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"reflection_{draw_no}.md"
    path.write_text(text, encoding="utf-8")

    # 누적 성과 JSON 저장
    perf_path = out / "strategy_performance.json"
    perf_path.write_text(json.dumps(perf, ensure_ascii=False, indent=2), encoding="utf-8")

    return path


def apply_strategy_adjustment(
    new_strategy_games: dict[str, int],
    config_path: str = "config/default.yaml",
) -> None:
    """config/default.yaml의 strategy_games 값을 업데이트."""
    import re
    text = Path(config_path).read_text(encoding="utf-8")

    for strategy, games in new_strategy_games.items():
        # strategy_games 섹션의 해당 전략 값만 교체
        pattern = rf"(strategy_games:.*?{strategy}:\s*)\d+"
        replacement = rf"\g<1>{games}"
        text = re.sub(pattern, replacement, text, flags=re.DOTALL)

    Path(config_path).write_text(text, encoding="utf-8")
