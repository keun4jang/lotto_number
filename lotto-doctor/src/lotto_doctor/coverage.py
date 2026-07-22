"""Portfolio coverage metrics and abbreviated wheel construction.

수학적 사실 (반드시 준수):

- 개별 티켓의 1등 확률은 고정되어 있으며 어떤 방법으로도 바꿀 수 없다.
- 서로 다른(distinct) k개 조합을 사면 1등 적중 확률은 정확히 k/8,145,060 이다.
  중복(동일) 조합은 절대 도움이 되지 않는다.
- 휠링(wheeling)/커버리지 최적화는 하위 등수 결과의 **분포(분산 구조)** 만
  바꿀 뿐, 기대값(EV)은 절대 바꾸지 못한다.

즉 이 모듈이 하는 일은 "당첨 확률 향상"이 아니라, 같은 EV 안에서
낮은 등수(5등: 3개 적중)가 최소 한 게임에서라도 나올 확률을 높이는
분산 구조 조정이다. 통계 기반 추천, 당첨 보장 없음.
"""

from __future__ import annotations

import random
from itertools import combinations
from typing import Any, Iterable, Sequence

TOTAL_COMBOS = 8_145_060  # C(45, 6)


# ---------------------------------------------------------------------------
# Coverage metrics
# ---------------------------------------------------------------------------


def portfolio_coverage_metrics(games: Sequence[Sequence[int]]) -> dict[str, Any]:
    """포트폴리오 커버리지 지표.

    Returns dict with:
      distinct_numbers: 게임들이 커버하는 서로 다른 번호 수 (5게임 최대 30)
      pairwise_overlaps: 게임 쌍별 공유 번호 수 리스트
      max_pairwise_overlap / mean_pairwise_overlap
      duplicate_games: 완전히 동일한 게임 쌍 수 (0이어야 함)
    """
    sets = [frozenset(g) for g in games]
    overlaps: list[int] = []
    duplicates = 0
    for a, b in combinations(sets, 2):
        ov = len(a & b)
        overlaps.append(ov)
        if a == b:
            duplicates += 1
    covered: set[int] = set()
    for s in sets:
        covered |= s
    return {
        "distinct_numbers": len(covered),
        "pairwise_overlaps": overlaps,
        "max_pairwise_overlap": max(overlaps) if overlaps else 0,
        "mean_pairwise_overlap": (sum(overlaps) / len(overlaps)) if overlaps else 0.0,
        "duplicate_games": duplicates,
    }


def prob_any_game_3plus(
    games: Sequence[Sequence[int]],
    n_samples: int = 200_000,
    seed: int = 0,
) -> float:
    """P(균등 무작위 추첨에서 최소 한 게임이 3개 이상 적중) — Monte Carlo 추정.

    이 확률은 게임 간 겹침 구조에 따라 달라진다(분산 구조).
    개별 게임의 P(3개 이상 적중)은 하이퍼기하 분포로 고정이며
    (약 1.86%), 겹침이 클수록 합집합 확률이 작아진다.
    EV는 어떤 구조에서도 동일하다.
    """
    rng = random.Random(seed)
    masks = [_mask(g) for g in games]
    pool = list(range(1, 46))
    hits = 0
    for _ in range(n_samples):
        draw_mask = _mask(rng.sample(pool, 6))
        for m in masks:
            if _popcount(m & draw_mask) >= 3:
                hits += 1
                break
    return hits / n_samples


def _mask(nums: Iterable[int]) -> int:
    m = 0
    for n in nums:
        m |= 1 << n
    return m


def _popcount(x: int) -> int:
    return bin(x).count("1")


# ---------------------------------------------------------------------------
# Abbreviated wheel (3-guarantee best effort)
# ---------------------------------------------------------------------------


def wheel_3subset_coverage(
    games: Sequence[Sequence[int]], pool: Sequence[int]
) -> float:
    """pool에서 뽑힌 3개 번호 조합 중, 어떤 게임 안에 함께 들어있는 비율.

    (풀 N개 중 임의의 3개가 추첨에 함께 나왔을 때 최소 한 게임이
    5등(3개 적중) 이상이 되도록 하는 3-subset 커버리지)
    """
    triples = list(combinations(sorted(pool), 3))
    if not triples:
        return 0.0
    game_sets = [frozenset(g) for g in games]
    covered = sum(
        1 for t in triples if any(set(t) <= gs for gs in game_sets)
    )
    return covered / len(triples)


def build_abbreviated_wheel(
    pool: Sequence[int],
    k_games: int,
) -> tuple[list[list[int]], float]:
    """축약 휠: pool(예: TOP-12 후보 번호)에서 k_games개의 서로 다른
    6번호 게임을 골라 3-subset 커버리지를 탐욕적으로 최대화한다.

    K=5, N=12 에서는 완전 3-guarantee가 불가능하다:
    C(12,3)=220 트리플, 게임당 최대 C(6,3)=20 트리플 → 5게임 최대 100개
    (45.5%). 따라서 best-effort 최대 커버리지를 구성하고 달성률을
    정직하게 반환한다. 완전 보장이 가능한 경우(예: N=6, K=1)에는 100%.

    결정적(deterministic): 후보를 사전순으로 순회하며 동점 시 사전순
    첫 조합을 선택한다.

    Returns (games, achieved_coverage_fraction).
    """
    pool = sorted(set(pool))
    if len(pool) < 6:
        raise ValueError("wheel pool must contain at least 6 numbers")

    all_games = [tuple(c) for c in combinations(pool, 6)]
    triple_index = {t: i for i, t in enumerate(combinations(pool, 3))}
    game_triples: list[set[int]] = [
        {triple_index[t] for t in combinations(g, 3)} for g in all_games
    ]

    selected: list[list[int]] = []
    selected_set: set[tuple[int, ...]] = set()
    covered: set[int] = set()

    for _ in range(k_games):
        best_idx = -1
        best_gain = -1
        for i, g in enumerate(all_games):
            if g in selected_set:
                continue  # 중복 게임 절대 금지
            gain = len(game_triples[i] - covered)
            if gain > best_gain:
                best_gain = gain
                best_idx = i
        if best_idx < 0:
            break
        g = all_games[best_idx]
        selected.append(list(g))
        selected_set.add(g)
        covered |= game_triples[best_idx]

    coverage = len(covered) / len(triple_index) if triple_index else 0.0
    return selected, coverage


def format_coverage_line(
    metrics: dict[str, Any],
    wheel_coverage: float | None = None,
) -> str:
    """추천 출력에 붙일 커버리지 리포트 한 줄 (한국어).

    주의: 커버리지는 하위 등수 결과의 분산 구조 지표일 뿐,
    개별 티켓 당첨 확률이나 EV를 바꾸지 않는다.
    """
    line = (
        f"커버리지: 서로 다른 번호 {metrics['distinct_numbers']}/30개, "
        f"게임 간 최대 겹침 {metrics['max_pairwise_overlap']}개"
    )
    if wheel_coverage is not None:
        line += f", 3개조합 커버리지 {wheel_coverage * 100:.1f}%"
    line += " (분산 구조 지표 — 확률/EV 향상 아님)"
    return line
