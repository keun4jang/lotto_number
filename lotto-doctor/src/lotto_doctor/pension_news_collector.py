"""연금복권720+ 당첨번호 뉴스 기반 자동 수집.

dhlottery.co.kr는 전체 도메인이 봇 차단(RSA 챌린지)되어 있어 직접 API 수집이
불가능하다. 대신 추첨 결과는 매 회차 다수 언론사가 즉시 보도하므로,
Google 뉴스 RSS(무인증, 무료, 키 불필요)에서 기사 제목을 파싱해 당첨번호를
교차검증 방식으로 추출한다.

신뢰도 확보 방법:
  - 서로 다른 언론사의 기사 제목에서 동일한 (회차, 조, 번호) 조합이
    2건 이상 일치할 때만 신뢰 (min_agreement).
  - 회차 번호는 최댓값(가장 최근) 기준으로 채택.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional
from xml.etree import ElementTree

import requests

from .pension_models import PensionDraw

_NEWS_RSS_URL = (
    "https://news.google.com/rss/search"
    "?q=%EC%97%B0%EA%B8%88%EB%B3%B5%EA%B6%8C720%2B%20%EB%8B%B9%EC%B2%A8%EB%B2%88%ED%98%B8"
    "&hl=ko&gl=KR&ceid=KR:ko"
)

_DRAW_RE = re.compile(r"(\d{2,4})\s*회")
_JO_NUMBER_RE = re.compile(r"(\d)\s*조\s*(\d{6})\s*번?")


def _fetch_rss(timeout: int = 10) -> str:
    resp = requests.get(_NEWS_RSS_URL, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.text


def _parse_titles(rss_xml: str) -> list[tuple[str, Optional[str]]]:
    """RSS XML에서 (title, pubDate) 목록을 추출."""
    root = ElementTree.fromstring(rss_xml)
    items = []
    for item in root.iter("item"):
        title_el = item.find("title")
        pubdate_el = item.find("pubDate")
        title = title_el.text if title_el is not None else None
        pubdate = pubdate_el.text if pubdate_el is not None else None
        if title:
            items.append((title, pubdate))
    return items


def _extract_candidates(titles: list[tuple[str, Optional[str]]]) -> Counter:
    """제목들에서 (draw_no, jo, number) 후보를 추출하고 빈도를 센다."""
    counter: Counter = Counter()
    for title, _ in titles:
        draw_match = _DRAW_RE.search(title)
        jo_num_match = _JO_NUMBER_RE.search(title)
        if not draw_match or not jo_num_match:
            continue
        draw_no = int(draw_match.group(1))
        jo = int(jo_num_match.group(1))
        number = jo_num_match.group(2)
        if not (1 <= jo <= 5) or not (1 <= draw_no < 5000):
            continue
        counter[(draw_no, jo, number)] += 1
    return counter


def _parse_pubdate(pubdate_str: Optional[str]) -> date:
    if pubdate_str:
        try:
            return datetime.strptime(pubdate_str, "%a, %d %b %Y %H:%M:%S %Z").date()
        except ValueError:
            pass
    return date.today()


def fetch_latest_pension_draw_from_news(
    min_agreement: int = 2,
    timeout: int = 10,
) -> Optional[PensionDraw]:
    """뉴스 기사 교차검증을 통해 최신 연금복권720+ 당첨 결과를 추정한다.

    서로 다른 기사에서 동일한 (회차, 조, 번호) 조합이 min_agreement건 이상
    일치해야 신뢰할 수 있는 결과로 채택한다. 실패 시 None 반환.
    """
    rss_xml = _fetch_rss(timeout=timeout)
    titles = _parse_titles(rss_xml)
    candidates = _extract_candidates(titles)

    if not candidates:
        return None

    # 회차 최댓값(최신) 기준으로 후보 필터링
    max_draw_no = max(draw_no for draw_no, _, _ in candidates)
    latest_candidates = {k: v for k, v in candidates.items() if k[0] == max_draw_no}

    best, count = max(latest_candidates.items(), key=lambda kv: kv[1])
    if count < min_agreement:
        return None

    draw_no, jo, number = best

    # 해당 회차를 언급한 기사 중 가장 이른 pubDate를 추첨일 추정치로 사용
    matching_dates = []
    for title, pubdate in titles:
        draw_match = _DRAW_RE.search(title)
        if draw_match and int(draw_match.group(1)) == draw_no:
            matching_dates.append(_parse_pubdate(pubdate))
    draw_date = min(matching_dates) if matching_dates else date.today()

    return PensionDraw(draw_no=draw_no, draw_date=draw_date, jo=jo, number=number)
