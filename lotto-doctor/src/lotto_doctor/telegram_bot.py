"""Telegram Bot API integration for Lotto Doctor."""

from __future__ import annotations

import time
from typing import Any

import requests

from .config import get_telegram_credentials

DISCLAIMER = (
    "⚠️ <b>주의</b>: 정상적인 로또에서 모든 6개 번호 조합의 1등 확률은 동일합니다. "
    "이 추천은 통계적 분석일 뿐이며 당첨을 보장하지 않습니다."
)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def send_message(text: str, parse_mode: str = "HTML") -> None:
    """Send a message via Telegram. Splits automatically if too long."""
    token, chat_id = get_telegram_credentials()
    max_len = 4096
    chunks = _split_message(text, max_len)
    for chunk in chunks:
        _send_chunk(token, chat_id, chunk, parse_mode)
        if len(chunks) > 1:
            time.sleep(0.5)


def _send_chunk(token: str, chat_id: str, text: str, parse_mode: str) -> None:
    url = _TELEGRAM_API.format(token=token, method="sendMessage")
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()


def _split_message(text: str, max_len: int) -> list[str]:
    """Split message on newlines to stay under max_len."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        if current_len + line_len > max_len and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def build_recommendation_message(
    target_draw_no: int,
    candidate_numbers: list[tuple[int, float]],
    games: list[Any],  # list[RecommendationGame]
    summary: dict[str, Any],
    draw_date: str = "",
) -> str:
    """Build the Telegram recommendation message."""
    lines: list[str] = [
        f"🎱 <b>로또 제{target_draw_no}회 추천번호</b>",
    ]
    if draw_date:
        lines.append(f"📅 추첨일: {draw_date} (토요일)")
    lines.append("")
    lines.append("📊 <b>후보번호 TOP 10</b>")
    top10_str = "  ".join(f"<b>{n}</b>" for n, _ in candidate_numbers[:10])
    lines.append(f"  {top10_str}")
    lines.append("")
    lines.append(f"🎯 <b>추천 {len(games)}게임</b>")

    for game in games:
        nums_str = " - ".join(f"{n:02d}" for n in game.numbers)
        lines.append(f"  <b>{game.game_label}게임</b> [{game.strategy}]  {nums_str}")

    lines.append("")
    lines.append("📈 <b>분석 요약</b>")
    for k, v in summary.items():
        lines.append(f"  • {k}: {v}")

    lines.append("")
    lines.append(DISCLAIMER)

    return "\n".join(lines)


def build_result_message(
    draw: Any,  # Draw
    games: list[Any],  # list[RecommendationGame]
    results: list[Any],  # list[EvaluationResult]
    cumulative: dict[str, int],
) -> str:
    """Build the Telegram result check message."""
    nums_str = " ".join(f"<b>{n}</b>" for n in draw.numbers)
    lines: list[str] = [
        f"🏆 <b>제{draw.draw_no}회 당첨결과</b>",
        f"  당첨번호: {nums_str}  +보너스 <b>{draw.bonus}</b>",
        "",
        "📋 <b>추천 게임 결과</b>",
    ]

    result_map = {r.game_label: r for r in results}
    best_match = 0
    for game in games:
        r = result_map.get(game.game_label)
        if r is None:
            continue
        prize_str = "" if r.rank_label == "no_prize" else f" → {r.rank_label}등"
        bonus_str = " 🎯보너스" if r.has_bonus_match and r.matched_count < 6 else ""
        lines.append(
            f"  {game.game_label}: {r.matched_count}개 적중{bonus_str}{prize_str}"
        )
        if r.matched_count > best_match:
            best_match = r.matched_count

    lines.append("")
    lines.append(f"✨ <b>최고 적중: {best_match}개</b>")
    lines.append("")
    lines.append("📊 <b>누적 성과</b>")
    for label, count in cumulative.items():
        lines.append(f"  {label}: {count}회")

    lines.append("")
    lines.append(DISCLAIMER)

    return "\n".join(lines)
