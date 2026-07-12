"""Telegram message formatting for Pension Lottery 720+."""

from __future__ import annotations

from .pension_models import PensionDraw, PensionEvaluationResult, PensionRecommendationGame


_RANK_EMOJI = {
    "1st": "🥇",
    "2nd": "🥈",
    "3rd": "🥉",
    "4th": "🎖",
    "5th": "✅",
    "6th": "🔵",
    "7th": "⚪",
    "no_prize": "❌",
}

_PRIZE_LABEL = {
    "1st": "월 700만원 × 20년",
    "2nd": "월 100만원 × 5년",
    "3rd": "1,000만원",
    "4th": "100만원",
    "5th": "10만원",
    "6th": "3,000원",
    "7th": "1,000원",
    "no_prize": "낙첨",
}


def build_pension_recommendation_message(
    draw_no: int,
    games: list[PensionRecommendationGame],
    draw_date: str = "",
) -> str:
    lines = [
        f"🎰 제{draw_no}회 연금복권720+ 추천번호",
    ]
    if draw_date:
        lines.append(f"📅 추첨일: {draw_date}")
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for g in games:
        lines.append(f"  [{g.game_label}] [{g.strategy}] {g.jo}조 - {g.number}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "⚠️ 통계 기반 추천이며 당첨을 보장하지 않습니다.",
        "모든 조합의 당첨 확률은 동일합니다.",
    ]
    return "\n".join(lines)


def build_pension_result_message(
    draw: PensionDraw,
    games: list[PensionRecommendationGame],
    results: list[PensionEvaluationResult],
) -> str:
    lines = [
        f"📋 제{draw.draw_no}회 연금복권720+ 결과",
        f"🎱 당첨번호: {draw.jo}조 - {draw.number}",
        "━━━━━━━━━━━━━━━━━━━━",
        "🎯 추천 결과",
        "",
    ]

    best_rank = "no_prize"
    rank_order = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "no_prize"]

    for g, r in zip(games, results):
        emoji = _RANK_EMOJI.get(r.prize_rank, "❌")
        prize = _PRIZE_LABEL.get(r.prize_rank, "낙첨")
        jo_note = "조✓" if r.jo_match else "조✗"
        lines.append(f"  [{g.game_label}] {g.jo}조-{g.number} ({jo_note}, 뒤{r.matched_suffix}자리) → {emoji} {prize}")
        if rank_order.index(r.prize_rank) < rank_order.index(best_rank):
            best_rank = r.prize_rank

    lines += [
        "",
        f"최고 결과: {_RANK_EMOJI.get(best_rank, '❌')} {_PRIZE_LABEL.get(best_rank, '낙첨')}",
        "━━━━━━━━━━━━━━━━━━━━",
        "⚠️ 통계 기반 추천이며 당첨을 보장하지 않습니다.",
    ]
    return "\n".join(lines)
