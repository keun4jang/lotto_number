"""Empirical crowd-behavior calibration from real Korean winner counts.

핵심 아이디어: 회차별 1등 당첨자 수는 그 회차 당첨 조합의 '인기도'에 대한
직접 측정치다. 균등 무작위 구매를 가정하면 기대 1등 당첨자 수는

    expected = (total_sales / 게임당 1,000원) / 8,145,060

이고, popularity_ratio = observed / expected 가 1보다 크면 그 조합의
특징(저번호, 패턴 등)이 실제 한국 구매자들에게 과선택된 것이다.

우아한 성질: 당첨 조합은 조합 공간에서 균등 무작위로 추출되므로, 이
표본은 인기도 함수에 대한 **비편향** 표본이다 (당첨 조합만 관측하지만
추첨 자체가 무작위이므로 선택 편향이 없다).

한계:
- 자동/반자동 구매 비중이 높아 조합 간 인기 편차가 크게 희석된다
  (관측되는 것은 '전체 구매 분포'이며 수동 편향은 그 일부).
- 기대 당첨자 수가 작은 회차는 포아송 잡음이 크다 → expected 로
  가중(WLS)하여 완화한다.
- 105회차 이전은 게임당 2,000원이라 판매액→게임 수 환산이 다르므로
  기본적으로 제외한다.

이 모듈은 popularity.py 의 추정 개선(기대 공동 당첨자 수)만을 위한
것이며, 당첨 확률과는 무관하다. (통계 기반 추천, EV 관점 비인기 조합
회피, 당첨 보장 없음.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .models import Draw
from .popularity import (
    arithmetic_pattern_score,
    consecutive_pair_count,
    grid_cluster_score,
    grid_line_score,
    human_pick_popularity_score,
    prev_draw_overlap_score,
    too_pretty_balance_score,
)

#: 로또 6/45 전체 조합 수
TOTAL_COMBINATIONS = 8_145_060

#: 게임당 가격이 1,000원이 된 첫 회차 (그 이전은 2,000원 → 기본 제외)
FIRST_1000_WON_DRAW = 106

#: 포아송 잡음이 지나치게 큰 회차를 제외하는 최소 기대 당첨자 수
DEFAULT_MIN_EXPECTED = 1.0


@dataclass(frozen=True)
class CalibrationRow:
    """한 회차의 인기도 측정치와 조합 피처."""

    draw_no: int
    numbers: tuple[int, ...]
    expected_winners: float
    observed_winners: int
    log_ratio: float          # log((observed + 0.5) / expected), 연속성 보정
    weight: float             # WLS 가중치 = expected_winners
    features: dict[str, float]
    model_score: float        # popularity.human_pick_popularity_score


def extract_features(
    nums: Sequence[int],
    prev_numbers: Sequence[int] | None = None,
) -> dict[str, float]:
    """popularity.py 모델 성분에 대응하는 조합 피처를 추출한다."""
    nums = list(nums)
    prev = list(prev_numbers) if prev_numbers else None
    return {
        "count_le_12": float(sum(1 for n in nums if n <= 12)),
        "count_13_31": float(sum(1 for n in nums if 13 <= n <= 31)),
        "has_7": 1.0 if 7 in nums else 0.0,
        "mult_of_7": float(sum(1 for n in nums if n % 7 == 0 and n != 7)),
        "consecutive_pairs": float(consecutive_pair_count(nums)),
        "grid_line": grid_line_score(nums),
        "grid_cluster": grid_cluster_score(nums),
        "arithmetic": arithmetic_pattern_score(nums),
        "pretty": too_pretty_balance_score(nums),
        "prev_overlap": prev_draw_overlap_score(nums, prev),
        "sum_norm": (sum(nums) - 138.0) / 100.0,
    }


def expected_first_winners(total_sales: int, game_price: int = 1000) -> float:
    """균등 무작위 구매 가정 하의 기대 1등 당첨자 수."""
    if total_sales <= 0 or game_price <= 0:
        return 0.0
    return (total_sales / game_price) / TOTAL_COMBINATIONS


def build_calibration_dataset(
    draws: Iterable[Draw],
    *,
    min_draw_no: int = FIRST_1000_WON_DRAW,
    min_expected: float = DEFAULT_MIN_EXPECTED,
) -> list[CalibrationRow]:
    """회차별 popularity ratio 데이터셋을 만든다 (순수 함수, DB/CLI 무관).

    1,000원 시대(기본 106회차~)만 사용하고, 기대 당첨자 수가
    min_expected 미만인 회차(포아송 잡음 과대)는 제외한다.
    """
    by_no: dict[int, Draw] = {d.draw_no: d for d in draws}
    rows: list[CalibrationRow] = []
    for draw_no in sorted(by_no):
        d = by_no[draw_no]
        if draw_no < min_draw_no:
            continue
        if d.total_sales is None or d.total_sales <= 0 or d.first_winners is None:
            continue
        exp = expected_first_winners(d.total_sales)
        if exp < min_expected:
            continue
        prev = by_no.get(draw_no - 1)
        prev_nums = list(prev.numbers) if prev else None
        nums = list(d.numbers)
        log_ratio = math.log((d.first_winners + 0.5) / exp)
        rows.append(
            CalibrationRow(
                draw_no=draw_no,
                numbers=tuple(nums),
                expected_winners=exp,
                observed_winners=int(d.first_winners),
                log_ratio=log_ratio,
                weight=exp,
                features=extract_features(nums, prev_nums),
                model_score=human_pick_popularity_score(nums, prev_nums),
            )
        )
    return rows


def fit_popularity_regression(
    rows: Sequence[CalibrationRow],
    feature_names: Sequence[str] | None = None,
) -> dict[str, tuple[float, float, float]]:
    """WLS 회귀: log_ratio ~ 피처. {이름: (계수, 표준오차, p값)} 반환.

    가중치는 expected_winners (포아송 분산 근사). numpy 만 사용한다.
    """
    import numpy as np
    from scipy import stats

    if not rows:
        return {}
    names = list(feature_names) if feature_names else list(rows[0].features)
    X = np.array([[1.0] + [r.features[k] for k in names] for r in rows])
    y = np.array([r.log_ratio for r in rows])
    w = np.array([r.weight for r in rows])
    XtW = X.T * w
    beta = np.linalg.solve(XtW @ X, XtW @ y)
    resid = y - X @ beta
    dof = max(len(rows) - X.shape[1], 1)
    sigma2 = float((resid**2 * w).sum() / dof)
    cov = np.linalg.inv(XtW @ X) * sigma2
    se = np.sqrt(np.diag(cov))
    out: dict[str, tuple[float, float, float]] = {}
    for i, k in enumerate(["const"] + names):
        t = beta[i] / se[i] if se[i] > 0 else 0.0
        p = 2.0 * float(stats.norm.sf(abs(t)))
        out[k] = (float(beta[i]), float(se[i]), p)
    return out


def model_measurement_correlation(
    rows: Sequence[CalibrationRow],
) -> tuple[float, float]:
    """(Pearson, Spearman) — 모델 인기 점수 vs 실측 log popularity ratio."""
    import numpy as np
    from scipy import stats

    if len(rows) < 3:
        return (0.0, 0.0)
    s = np.array([r.model_score for r in rows])
    y = np.array([r.log_ratio for r in rows])
    if float(np.std(s)) < 1e-12 or float(np.std(y)) < 1e-12:
        return (0.0, 0.0)  # 상수 입력이면 상관 정의 불가
    pearson = float(np.corrcoef(s, y)[0, 1])
    spearman = float(stats.spearmanr(s, y).statistic)
    return (pearson, spearman)
