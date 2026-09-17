# -*- coding: utf-8 -*-
"""Pexels 사진 검색. 카드 썸네일 배경으로 쓴다.

왜 Pexels 인가
    네이버 이미지·포토뉴스·블로그 사진은 저작권이 있어 상업 사이트에 못 쓴다.
    Pexels 는 상업 이용이 무료이고 출처 표기 의무도 없다(그래도 촬영자 이름은
    기사에 남긴다). 키 없이 되는 Openverse 도 봤지만, "candlestick" 을 검색하면
    캔들스틱 파크(야구장)와 라벤더 사진이 나와서 쓸 수 없었다.

키는 config.json 의 pexels_api_key. 없으면 photo() 가 None 을 돌려주고,
카드는 사진 없이 차트만으로 그려진다 — 사진이 없다고 기사가 실패하면 안 된다.
"""
import json
import urllib.parse
import urllib.request

ENDPOINT = ("https://api.pexels.com/v1/search?per_page={n}&orientation=landscape"
            "&query={q}")

# 지표별 검색어. 아무 사진이나 붙이면 장식이 되므로 소재를 지표에 맞춘다.
QUERIES = {
    "KOSPI": "stock market trading screen",
    "원/달러 환율": "currency exchange finance",
    "비트코인": "bitcoin cryptocurrency",
}
DEFAULT_QUERY = "financial market chart"


def photo(cfg, query, index=0, timeout=20):
    """{url, by} 또는 None. 실패는 조용히 None 이다."""
    key = (cfg or {}).get("pexels_api_key", "")
    if not key:
        return None
    # per_page 를 넉넉히 잡는다. 5로 좁히면 같은 질의에도 결과 구성이 달라져
    # 색이 밋밋한 사진이 1순위로 오는 일이 있었다.
    url = ENDPOINT.format(n=max(index + 1, 8), q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={
        "Authorization": key, "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            photos = json.loads(r.read().decode("utf-8")).get("photos", [])
    except Exception:
        return None
    if not photos:
        return None
    p = photos[min(index, len(photos) - 1)]
    return {"url": p["src"]["landscape"], "by": p.get("photographer", ""),
            "page": p.get("url", "")}


def for_indicator(cfg, name, index=0):
    return photo(cfg, QUERIES.get(name, DEFAULT_QUERY), index)
