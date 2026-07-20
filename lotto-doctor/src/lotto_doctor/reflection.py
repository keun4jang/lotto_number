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
) -> dict[str, float] | None:
    """Shrinkage 기반 전략 배분 조정.

    - reliability = n / (n + shrinkage_k): 샘플 적을수록 기본 배분에 수렴
    - rare_event_cap: match_4 이상 희귀 이벤트 과대반영 방지
    - 변화량 max_adjustment 이내 제한
    - 음수 방지, 합계 정규화
    Returns None if not enough data.
    """
    ref_cfg = cfg.get("reflection", {})
    min_samples: int = ref_cfg.get("min_samples", 30)
    shrinkage_k: int = ref_cfg.get("shrinkage_k", 20)
    max_adj: float = ref_cfg.get("max_adjustment", 0.05)
    rare_cap: int = ref_cfg.get("rare_event_cap", 2)

    current_games: dict[str, int] = cfg["generator"]["strategy_games"]
    total_current = sum(current_games.values())
    if total_current == 0:
        return None

    active_strategies = [s for s, n in current_games.items() if n > 0]
    valid = {s: perf[s] for s in active_strategies if s in perf and perf[s]["total_games"] >= min_samples}
    if len(valid) < max(2, len(active_strategies) // 2):
        return None  # 데이터 부족

    base_ratios = {s: current_games[s] / total_current for s in current_games}

    # 성과 점수: avg_match + 희귀 이벤트 보너스 (cap 적용) — 유효 전략 먼저 계산
    valid_scores: dict[str, float] = {}
    for s, p in valid.items():
        base_score = p["avg_match"]
        rare_bonus = min(p.get("match_4", 0) * 0.1 + p.get("match_5", 0) * 0.5, rare_cap * 0.1)
        n = p["total_games"]
        reliability = n / (n + shrinkage_k)
        # 기본 배분 대비 성과 편차에 reliability 적용
        valid_scores[s] = base_score + reliability * rare_bonus

    mean_valid_score = sum(valid_scores.values()) / len(valid_scores)

    # 데이터 부족한 활성 전략은 중립 점수(유효 전략 평균, 같은 단위)로 채우고,
    # 비활성(0게임) 전략은 0점 → 배분 0 유지 (KeyError 방지)
    perf_scores: dict[str, float] = {}
    for s in current_games:
        if s in valid_scores:
            perf_scores[s] = valid_scores[s]
        elif s in active_strategies:
            perf_scores[s] = mean_valid_score
        else:
            perf_scores[s] = 0.0

    total_perf = sum(perf_scores.values())
    if total_perf <= 0:
        return None

    target_ratios = {s: perf_scores[s] / total_perf for s in current_games}

    adjusted = {}
    for s in current_games:
        base = base_ratios.get(s, 0.0)
        target = target_ratios.get(s, base)
        n = valid.get(s, {}).get("total_games", 0)
        reliability = n / (n + shrinkage_k)
        delta = reliability * (target - base)
        delta = max(-max_adj, min(max_adj, delta))
        adjusted[s] = max(0.0, base + delta)

    # 정규화 후 합계 total_current 맞추기: largest-remainder(Hamilton) 방식
    # → 합계가 항상 보존되고, 특정 전략에 반올림 잔여분이 몰리지 않는다.
    total_adj = sum(adjusted.values())
    if total_adj == 0:
        return None

    quotas = {s: adjusted[s] / total_adj * total_current for s in adjusted}
    new_games: dict[str, int] = {s: int(quotas[s]) for s in quotas}  # floor
    shortfall = total_current - sum(new_games.values())

    # 소수부가 큰 순서대로 1게임씩 배분 (동률 시 quota 큰 쪽 우선 → 결정적)
    # quota가 0인(비활성) 전략에는 잔여분을 주지 않는다.
    order = sorted(
        (s for s in quotas if quotas[s] > 0),
        key=lambda s: (quotas[s] - int(quotas[s]), quotas[s]),
        reverse=True,
    )
    if shortfall < 0 or shortfall > len(order):
        return None  # 수치 이상 (방어)
    for s in order[:shortfall]:
        new_games[s] += 1

    # 합계 검증
    if sum(new_games.values()) != total_current:
        return None

    return new_games


def generate_reflection_text(
    draw_no: int,
    draw_numbers: list[int],
    bonus: int,
    games: list[dict],
    perf: dict[str, dict],
    new_strategy_games: dict[str, float] | None,
    old_strategy_games: dict[str, int] | None = None,
    new_model_version: str | None = None,
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
    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("🔧 시스템 자동 조정 (self-tune)\n")
    if new_strategy_games:
        lines.append("성과 기반으로 다음 주 전략 배분 조정:")
        for s, g in new_strategy_games.items():
            prev = old_strategy_games.get(s, "?") if old_strategy_games else "?"
            arrow = f" ({prev}→{g})" if old_strategy_games and prev != g else f" (유지: {g})"
            lines.append(f"  {s}{arrow}게임")
        ver_note = f" (→ {new_model_version})" if new_model_version else ""
        lines.append(f"\n✅ config/default.yaml 자동 반영 완료{ver_note}")
    else:
        lines.append("데이터 축적 중 (조정 보류)")
        lines.append("  → 전략별 최소 30게임 이상 평가 데이터 필요")

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


def _bump_patch_version(current: str) -> str:
    """be-v1.1.0-ev → be-v1.1.1-ev 형식으로 patch 버전 증가."""
    import re
    m = re.match(r"^(be-v\d+\.\d+\.)(\d+)(-.+)?$", current)
    if not m:
        return current
    prefix, patch, suffix = m.group(1), int(m.group(2)), m.group(3) or ""
    return f"{prefix}{patch + 1}{suffix}"


def apply_strategy_adjustment(
    new_strategy_games: dict[str, int],
    config_path: str = "config/default.yaml",
) -> str:
    """config/default.yaml의 strategy_games 값을 업데이트하고 patch 버전을 올린다.

    실제 변경이 있을 때만 model_version을 bump한다.
    Returns: new model_version string
    """
    import re
    text = Path(config_path).read_text(encoding="utf-8")
    original = text

    for strategy, games in new_strategy_games.items():
        pattern = rf"(strategy_games:.*?{strategy}:\s*)\d+"
        replacement = rf"\g<1>{games}"
        text = re.sub(pattern, replacement, text, flags=re.DOTALL)

    # 전략 배분이 실제로 바뀐 경우에만 버전 bump
    version_bumped = ""
    if text != original:
        ver_m = re.search(r'model_version:\s*"([^"]+)"', text)
        if ver_m:
            old_ver = ver_m.group(1)
            new_ver = _bump_patch_version(old_ver)
            text = text.replace(f'model_version: "{old_ver}"', f'model_version: "{new_ver}"', 1)
            version_bumped = new_ver

    Path(config_path).write_text(text, encoding="utf-8")
    return version_bumped
