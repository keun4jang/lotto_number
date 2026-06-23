"""Report generation for Lotto Doctor (CSV, Markdown)."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import EvaluationResult, RecommendationGame


def _reports_dir(cfg: dict[str, Any]) -> Path:
    p = Path(cfg.get("reporter", {}).get("reports_dir", "reports"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_recommendation_csv(
    games: list[RecommendationGame],
    draw_no: int,
    cfg: dict[str, Any],
) -> Path:
    """Save recommendation games to CSV."""
    out_dir = _reports_dir(cfg)
    path = out_dir / f"recommendation_{draw_no}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["game_label", "strategy", "n1", "n2", "n3", "n4", "n5", "n6"])
        for g in games:
            writer.writerow([g.game_label, g.strategy] + g.numbers)
    return path


def save_recommendation_markdown(
    games: list[RecommendationGame],
    candidate_numbers: list[tuple[int, float]],
    draw_no: int,
    cfg: dict[str, Any],
) -> Path:
    """Save recommendation report as Markdown."""
    out_dir = _reports_dir(cfg)
    path = out_dir / f"recommendation_{draw_no}.md"
    lines = [
        f"# 제{draw_no}회 로또 추천번호",
        f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "> **주의**: 정상적인 로또에서 모든 6개 번호 조합의 1등 확률은 동일합니다.",
        "> 이 추천은 통계적 분석일 뿐이며 당첨을 보장하지 않습니다.",
        "",
        "## 후보번호 TOP 10",
        "",
        "| 순위 | 번호 | 점수 |",
        "|------|------|------|",
    ]
    for rank, (num, score) in enumerate(candidate_numbers[:10], 1):
        lines.append(f"| {rank} | {num} | {score:.4f} |")
    lines.extend([
        "",
        "## 추천 10게임",
        "",
        "| 게임 | 전략 | 번호 |",
        "|------|------|------|",
    ])
    for g in games:
        nums_str = " - ".join(f"{n:02d}" for n in g.numbers)
        lines.append(f"| {g.game_label} | {g.strategy} | {nums_str} |")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def save_evaluation_markdown(
    games: list[RecommendationGame],
    results: list[EvaluationResult],
    draw_no: int,
    cfg: dict[str, Any],
) -> Path:
    """Save evaluation results as Markdown."""
    out_dir = _reports_dir(cfg)
    path = out_dir / f"evaluation_{draw_no}.md"
    result_map = {r.game_label: r for r in results}
    lines = [
        f"# 제{draw_no}회 추천 평가결과",
        f"평가일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| 게임 | 번호 | 적중 | 보너스 | 등수 |",
        "|------|------|------|--------|------|",
    ]
    for g in games:
        r = result_map.get(g.game_label)
        if r is None:
            continue
        nums_str = " ".join(f"{n:02d}" for n in g.numbers)
        bonus_str = "O" if r.has_bonus_match else "-"
        lines.append(f"| {g.game_label} | {nums_str} | {r.matched_count} | {bonus_str} | {r.rank_label} |")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
