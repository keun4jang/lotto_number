"""Pension Lottery 720+ result evaluator."""

from __future__ import annotations

from .pension_models import PensionDraw, PensionEvaluationResult, PensionRecommendationGame


def _count_matching_suffix(recommended: str, actual: str) -> int:
    """Count how many trailing digits match between two 6-digit strings.

    끝자리(뒤)부터 앞으로 비교하며 처음 불일치에서 멈춘다.
    문자열 끝 기준으로 비교하므로 길이가 어긋난 입력에도 뒤자리 의미가 유지된다.
    """
    rec = recommended.strip().zfill(6)
    act = actual.strip().zfill(6)
    count = 0
    for i in range(1, 7):
        if rec[-i] == act[-i]:
            count += 1
        else:
            break
    return count


def _get_prize_rank(jo_match: bool, matched_suffix: int) -> str:
    """Determine prize rank based on 연금복권720+ rules."""
    if jo_match and matched_suffix == 6:
        return "1st"   # 조+6자리 완전 일치 → 월 700만원 × 20년
    if not jo_match and matched_suffix == 6:
        return "2nd"   # 6자리만 일치 → 월 100만원 × 5년
    if matched_suffix == 5:
        return "3rd"   # 뒤 5자리 → 1,000만원
    if matched_suffix == 4:
        return "4th"   # 뒤 4자리 → 100만원
    if matched_suffix == 3:
        return "5th"   # 뒤 3자리 → 10만원
    if matched_suffix == 2:
        return "6th"   # 뒤 2자리 → 3,000원
    if matched_suffix == 1:
        return "7th"   # 뒤 1자리 → 1,000원
    return "no_prize"


def evaluate_pension_run(
    games: list[PensionRecommendationGame],
    draw: PensionDraw,
) -> list[PensionEvaluationResult]:
    results = []
    for game in games:
        jo_match = game.jo == draw.jo
        matched_suffix = _count_matching_suffix(game.number, draw.number)
        rank = _get_prize_rank(jo_match, matched_suffix)
        results.append(
            PensionEvaluationResult(
                run_id=game.run_id,
                game_label=game.game_label,
                jo_match=jo_match,
                matched_suffix=matched_suffix,
                prize_rank=rank,
            )
        )
    return results
