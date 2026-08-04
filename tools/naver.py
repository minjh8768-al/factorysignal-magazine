# -*- coding: utf-8 -*-
"""네이버 뉴스 검색. factcheck.py가 기사의 고유명사·수치를 대조하는 데 쓴다.

키 발급: https://developers.naver.com 앱등록 → 사용 API "검색"
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://openapi.naver.com/v1/search/news.json?display={n}&sort=sim&query={q}"

_TAG = re.compile(r"<[^>]+>")
_ENTITIES = {"&quot;": '"', "&amp;": "&", "&lt;": "<", "&gt;": ">",
             "&apos;": "'", "&#39;": "'", "&nbsp;": " "}


def _clean(text):
    text = _TAG.sub("", text or "")
    for ent, ch in _ENTITIES.items():
        text = text.replace(ent, ch)
    return text.strip()


def search(cfg, query, display=5, timeout=20):
    """(총건수, [(제목, 요약), ...]) 를 반환한다. 실패하면 (None, 오류메시지)."""
    if not cfg.get("naver_client_id") or not cfg.get("naver_client_secret"):
        return None, "config.json에 naver_client_id / naver_client_secret이 없습니다."
    url = ENDPOINT.format(n=display, q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={
        "X-Naver-Client-Id": cfg["naver_client_id"],
        "X-Naver-Client-Secret": cfg["naver_client_secret"],
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    items = [(_clean(i.get("title")), _clean(i.get("description")))
             for i in data.get("items", [])]
    return data.get("total", 0), items
