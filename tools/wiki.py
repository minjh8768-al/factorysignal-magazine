# -*- coding: utf-8 -*-
"""위키백과 조회. 인물·기관 표기와 직함을 검증한다. API 키가 필요 없다.

인물 검증에서 뉴스 검색보다 신호가 깔끔하다. 뉴스는 다른 언론의 오타까지 함께 잡히지만
(곽상원 67건) 위키백과는 문서 자체가 없다. 게다가 첫 문단에 직함이 들어 있어
기사가 쓴 직함이 맞는지도 볼 수 있다.

실측:
  곽상언 -> "제22대 국회의원, 노무현 제16대 대통령의 사위"
  곽상원 -> 문서 없음
  케빈 워시 -> "2026년부터 연방준비제도 의장"
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API = ("https://{lang}.wikipedia.org/w/api.php?action=query&format=json"
       "&prop=extracts&exintro=1&explaintext=1&redirects=1&titles={title}")
SEARCH = ("https://{lang}.wikipedia.org/w/api.php?action=query&format=json"
          "&list=search&srlimit=3&srsearch={q}")
UA = {"User-Agent": "factorysignal-magazine/1.0 (factcheck; contact via repo)"}

# 위키백과는 빠르게 연달아 부르면 429를 준다. 실측에서 한 기사(15항목)를 쉬지 않고
# 조회하다 중간에 막혔다. 호출 간 최소 간격을 둔다.
MIN_INTERVAL = 0.4
_last_call = [0.0]
_lock = threading.Lock()

# 동명이인 안내 페이지. 내용이 없으므로 검증에 쓸 수 없다.
DISAMBIG = ("다음 사람을 가리킨다", "동명이인", "다음과 같", "may refer to",
            "may also refer to")


def _throttle():
    with _lock:
        gap = time.monotonic() - _last_call[0]
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_call[0] = time.monotonic()


def _get(url, timeout=20):
    _throttle()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def is_disambiguation(extract):
    return bool(extract) and any(k in extract for k in DISAMBIG)


def lookup(term, lang="ko", timeout=20):
    """문서 첫 문단을 반환한다. 없으면 None. 조회 실패면 예외 대신 None을 준다.

    (본문, None)        문서 있음
    (None, None)        문서 없음
    (None, 오류메시지)   조회 실패
    """
    url = API.format(lang=lang, title=urllib.parse.quote(term))
    try:
        data = _get(url, timeout)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    pages = data.get("query", {}).get("pages", {})
    for _, page in pages.items():
        if "missing" in page:
            return None, None
        extract = (page.get("extract") or "").replace("\n", " ").strip()
        if extract:
            return extract, None
    return None, None


def search(term, lang="ko", timeout=20):
    """비슷한 제목을 찾는다. 오기일 때 올바른 표기를 제안하는 데 쓴다."""
    url = SEARCH.format(lang=lang, q=urllib.parse.quote(term))
    try:
        data = _get(url, timeout)
    except Exception:
        return []
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def title_matches(extract, claimed_title):
    """기사가 쓴 직함이 위키백과 첫 문단에 나타나는지.

    "연준 의장"처럼 줄여 쓰는 경우가 많아 2자 이상 토막으로 나눠 하나라도 걸리면
    맞는 것으로 본다. 판정이 아니라 힌트다.
    """
    if not extract or not claimed_title:
        return False
    parts = [p for p in claimed_title.replace("·", " ").split() if len(p) >= 2]
    return any(p in extract for p in parts) if parts else False
