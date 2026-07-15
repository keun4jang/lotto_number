"""Tests for pension_news_collector (뉴스 기반 자동 수집)."""

from __future__ import annotations

from datetime import date

from lotto_doctor.pension_news_collector import (
    _extract_candidates,
    _parse_titles,
    backfill_pension_history,
    fetch_latest_pension_draw_from_news,
    fetch_pension_draw_by_number,
)

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>[종합]323회 연금복권720+ 당첨번호확인 및 로또 당첨번호 조회! - 이코노미톡뉴스</title>
<pubDate>Thu, 09 Jul 2026 20:00:00 GMT</pubDate>
</item>
<item>
<title>제323회 연금복권720+ 1등 4조 604270번…월 700만 원 20년 수령 - 캐어유 뉴스</title>
<pubDate>Thu, 09 Jul 2026 20:41:02 GMT</pubDate>
</item>
<item>
<title>연금복권720+ 323회 1등 당첨번호 4조 604270 1등 2명 - 스페셜타임스</title>
<pubDate>Thu, 09 Jul 2026 21:10:00 GMT</pubDate>
</item>
<item>
<title>322회 연금복권 1등 당첨 - bntnews.co.kr</title>
<pubDate>Thu, 02 Jul 2026 20:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


def test_parse_titles():
    items = _parse_titles(_SAMPLE_RSS)
    assert len(items) == 4
    assert "323회" in items[0][0]


def test_extract_candidates_cross_validation():
    items = _parse_titles(_SAMPLE_RSS)
    candidates = _extract_candidates(items)
    assert candidates[(323, 4, "604270")] == 2


def test_fetch_latest_pension_draw_from_news(monkeypatch):
    import lotto_doctor.pension_news_collector as mod

    monkeypatch.setattr(mod, "_fetch_rss", lambda timeout=10: _SAMPLE_RSS)

    draw = fetch_latest_pension_draw_from_news(min_agreement=2)
    assert draw is not None
    assert draw.draw_no == 323
    assert draw.jo == 4
    assert draw.number == "604270"
    assert draw.draw_date == date(2026, 7, 9)


def test_fetch_latest_pension_draw_insufficient_agreement(monkeypatch):
    import lotto_doctor.pension_news_collector as mod

    single_match_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>제100회 연금복권720+ 1등 3조 111222번 - 뉴스사</title>
<pubDate>Thu, 01 Jan 2026 20:00:00 GMT</pubDate>
</item>
</channel></rss>
"""
    monkeypatch.setattr(mod, "_fetch_rss", lambda timeout=10: single_match_rss)

    draw = fetch_latest_pension_draw_from_news(min_agreement=2)
    assert draw is None


def test_fetch_latest_pension_draw_no_candidates(monkeypatch):
    import lotto_doctor.pension_news_collector as mod

    empty_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel></channel></rss>
"""
    monkeypatch.setattr(mod, "_fetch_rss", lambda timeout=10: empty_rss)

    draw = fetch_latest_pension_draw_from_news()
    assert draw is None


_SAMPLE_RSS_BY_DRAW = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>제322회 연금복권720+ 1등 2조 119392번…월 700만 원 20년 수령 - 캐어유 뉴스</title>
<pubDate>Thu, 02 Jul 2026 20:41:02 GMT</pubDate>
</item>
<item>
<title>연금복권 720 322회 당첨결과, 1등 2명·2등 8명·보너스 1명(종합) - 톱스타뉴스</title>
<pubDate>Thu, 02 Jul 2026 20:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


def test_fetch_pension_draw_by_number(monkeypatch):
    import lotto_doctor.pension_news_collector as mod

    monkeypatch.setattr(mod, "_fetch_rss_for_draw", lambda draw_no, timeout=10: _SAMPLE_RSS_BY_DRAW)

    draw = fetch_pension_draw_by_number(322)
    assert draw is not None
    assert draw.draw_no == 322
    assert draw.jo == 2
    assert draw.number == "119392"


def test_fetch_pension_draw_by_number_no_match(monkeypatch):
    import lotto_doctor.pension_news_collector as mod

    unrelated_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>제999회 연금복권720+ 1등 1조 000000번 - 뉴스사</title>
<pubDate>Thu, 01 Jan 2026 20:00:00 GMT</pubDate>
</item>
</channel></rss>
"""
    monkeypatch.setattr(mod, "_fetch_rss_for_draw", lambda draw_no, timeout=10: unrelated_rss)

    draw = fetch_pension_draw_by_number(322)
    assert draw is None


def test_backfill_pension_history(monkeypatch):
    import lotto_doctor.pension_news_collector as mod

    def fake_fetch(draw_no, timeout=10):
        if draw_no == 321:
            return None  # simulate a missing/unfound draw
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>제{draw_no}회 연금복권720+ 1등 3조 555555번 - 뉴스사</title>
<pubDate>Thu, 01 Jan 2026 20:00:00 GMT</pubDate>
</item>
</channel></rss>
"""

    def fake_fetch_pension_draw_by_number(draw_no, timeout=10):
        rss = fake_fetch(draw_no)
        if rss is None:
            return None
        titles = mod._parse_titles(rss)
        from collections import Counter
        counter = Counter()
        for title, _ in titles:
            dm = mod._DRAW_RE.search(title)
            jm = mod._JO_NUMBER_RE.search(title)
            if dm and jm and int(dm.group(1)) == draw_no:
                counter[(int(jm.group(1)), jm.group(2))] += 1
        if not counter:
            return None
        (jo, number), _ = counter.most_common(1)[0]
        from lotto_doctor.pension_models import PensionDraw
        from datetime import date
        return PensionDraw(draw_no=draw_no, draw_date=date.today(), jo=jo, number=number)

    monkeypatch.setattr(mod, "fetch_pension_draw_by_number", fake_fetch_pension_draw_by_number)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    draws = backfill_pension_history(latest_draw_no=323, count=5, delay_sec=0)
    draw_nos = sorted(d.draw_no for d in draws)
    assert 321 not in draw_nos
    assert draw_nos == [318, 319, 320, 322]
