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


# ── 영상 요약 기사 카드 사진 (2026-10-20) ─────────────────────────────
# 새 기사는 Gemini가 photo_query(영문 검색어)를 준다. 그게 없는 예전 기사는 제목 속
# 핵심어 → 꼬리표 순으로 검색어를 정한다. 스톡 사진에는 특정 인물이 없으므로 인물명이
# 아니라 장면(장소·사물)으로 찾는다.
TITLE_QUERIES = (
    ("비트코인", "bitcoin cryptocurrency"), ("이더리움", "ethereum cryptocurrency"),
    ("스테이블코인", "digital currency payment"), ("가상자산", "cryptocurrency trading"),
    ("코인", "cryptocurrency coins"), ("ETF", "stock exchange trading floor"),
    ("반도체", "semiconductor chip factory"), ("AI", "artificial intelligence technology"),
    ("데이터센터", "data center servers"), ("코스피", "stock market chart"),
    ("증시", "stock market trading screen"), ("국채", "government bonds finance"),
    ("금리", "central bank interest rates"), ("연준", "federal reserve building"),
    ("FOMC", "federal reserve building"), ("물가", "grocery prices inflation"),
    ("CPI", "grocery prices inflation"), ("PPI", "factory production line"),
    ("환율", "currency exchange money"), ("부동산", "apartment buildings seoul"),
    ("트럼프", "white house washington"), ("백악관", "white house washington"),
    ("중간선거", "american election voting"), ("이스라엘", "middle east conflict"),
    ("가자", "middle east conflict"), ("레바논", "middle east conflict"),
    ("이란", "middle east conflict"), ("우크라이나", "war ruins europe"),
    ("관광", "tourism travel desert"), ("국회", "parliament building"),
    ("대통령", "presidential office korea"), ("재판", "courtroom gavel justice"),
    ("징역", "courtroom gavel justice"), ("검찰", "courtroom gavel justice"),
    ("야구", "baseball game stadium"), ("KBO", "baseball game stadium"),
    ("축구", "soccer football match"), ("아시안게임", "athletes sports competition"),
    ("배드민턴", "badminton match"), ("농구", "basketball game"), ("롤", "esports gaming"),
    ("인스타그램", "smartphone social media"), ("쇼핑", "online shopping ecommerce"),
    ("아마존", "online shopping ecommerce"), ("스타트업", "startup office team"),
)
EYEBROW_QUERIES = {
    "시장": "stock market trading", "금리·정책": "central bank interest rates",
    "산업·기업": "modern factory industry", "데이터분석": "financial market chart",
    "규제·정책": "cryptocurrency regulation law", "산업": "blockchain technology",
    "국내정치": "parliament building", "정책": "government policy meeting",
    "안보·국방": "military security", "법·사법": "courtroom gavel justice",
    "국제정세": "world news globe", "미국": "white house washington",
    "세계경제": "global trade shipping containers", "종합": "sports stadium crowd",
    "야구": "baseball game stadium", "축구": "soccer football match",
    "농구·배구": "basketball game", "창업·투자": "startup office team",
    "AI·테크": "artificial intelligence technology", "전략": "business strategy meeting",
}


def query_for(title, eyebrow, category=""):
    for word, q in TITLE_QUERIES:
        if word in (title or ""):
            return q
    return EYEBROW_QUERIES.get(eyebrow, "news newspaper")


def pick_index(slug, n):
    """같은 검색어를 쓰는 기사끼리 같은 사진이 반복되지 않게 slug로 결과 순번을 고른다."""
    return sum(ord(c) for c in slug) % max(n, 1)
