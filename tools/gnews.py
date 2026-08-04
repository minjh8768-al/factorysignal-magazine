# -*- coding: utf-8 -*-
"""Google News RSS 검색. 해외 사건·날짜·수치 대조용. API 키가 필요 없다.

네이버 뉴스는 국내 보도가 강하지만 해외 사안은 얇다. 영어권 영상을 다루기 시작하면
Google News 쪽 근거가 필요해진다. Custom Search API는 무료 100회/일로 빡빡한데
RSS는 키 없이 쓸 수 있다.
"""
import re
import urllib.parse
import urllib.request

FEED = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
UA = {"User-Agent": "factorysignal-magazine/1.0 (factcheck; contact via repo)"}

LOCALES = {
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "ko": {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
}

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_TITLE = re.compile(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", re.S)
_SOURCE = re.compile(r"<source[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</source>", re.S)
_ENTITIES = {"&quot;": '"', "&amp;": "&", "&lt;": "<", "&gt;": ">",
             "&apos;": "'", "&#39;": "'", "&nbsp;": " "}


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    for ent, ch in _ENTITIES.items():
        text = text.replace(ent, ch)
    return text.strip()


def search(query, lang="en", limit=3, timeout=20):
    """(건수, [(제목, 출처), ...]) 를 반환한다. 실패하면 (None, 오류메시지)."""
    loc = LOCALES.get(lang, LOCALES["en"])
    url = FEED.format(q=urllib.parse.quote(query), **loc)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml = resp.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

    items = _ITEM.findall(xml)
    rows = []
    for item in items[:limit]:
        title = _TITLE.search(item)
        source = _SOURCE.search(item)
        rows.append((_clean(title.group(1)) if title else "",
                     _clean(source.group(1)) if source else ""))
    return len(items), rows
