# -*- coding: utf-8 -*-
"""카테고리별 유튜브 영상 후보 수집.

    py -3 collect.py                모든 카테고리
    py -3 collect.py 스포츠 세계      지정한 카테고리만
    py -3 collect.py --json         표 없이 JSON만 (다른 도구에서 쓸 때)

결과를 _candidates.json에 저장한다. 번호를 골라 draft.py에 넘긴다.

유튜브 검색결과 페이지를 읽는다(API 키 불필요). 유튜브가 페이지 구조를 바꾸면
ytInitialData를 못 찾을 수 있고, 그때는 그렇게 안내하고 멈춘다.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_candidates.json")

# 카테고리별 검색어. 한 카테고리에 여러 개를 던져 후보 폭을 넓힌다.
QUERIES = {
    "정치": ["국회 여야 쟁점", "정치 뉴스 분석", "국회 본회의 법안", "대통령실 현안"],
    "경제": ["금리 물가 전망 분석", "환율 증시 전망", "경제 뉴스 해설", "부동산 시장 분석"],
    # 암호화폐는 업로드날짜순으로 뽑으면 개인 트레이딩 채널이 상위를 덮는다.
    # 제도·규제·시장구조 쪽 검색어로 기울여 둔다.
    "암호화폐": ["가상자산 규제 정책", "스테이블코인 제도", "비트코인 시장 구조 해설",
               "가상자산 거래소 뉴스"],
    "스포츠": ["프로야구 이슈 정리", "축구 국가대표 소식", "스포츠 뉴스 브리핑", "KBO 순위 경쟁"],
    "세계": ["국제뉴스 브리핑", "세계는 지금", "국제 이슈 정리", "특파원 현장"],
    "스타트업": ["스타트업 대표 인터뷰", "창업 스토리 인터뷰", "EO 스타트업", "티타임즈 스타트업"],
}

# 영어권 검색어. 국내 유튜브에 쓸 만한 영상이 얇은 카테고리(스포츠·세계)를 메운다.
# 정치는 국내 정당·국회 사안이라 한국어만 쓴다. 해외 정치 영상은 '세계'로 분류된다.
EN_QUERIES = {
    "경제": ["global economy analysis", "central bank policy explained",
            "inflation outlook analysis"],
    "암호화폐": ["crypto regulation explained", "bitcoin market analysis",
               "stablecoin policy"],
    "스포츠": ["premier league tactical analysis", "champions league review",
             "mlb analysis breakdown"],
    "세계": ["geopolitics explained", "world news analysis", "foreign policy briefing"],
    "스타트업": ["startup founder interview", "venture capital interview",
               "how they built it startup"],
}

# 매체 성격에 맞지 않거나 요약할 발언이 없는 영상을 걸러낸다.
# 아래 목록은 실제 검색 결과를 보고 채운 것이다. 새로 걸러야 할 채널이 보이면 여기에
# 추가하면 된다 — 이 필터가 collect.py의 유일한 튜닝 지점이다.
#
# 걸러내는 이유:
#   승부예측·베팅류  매체 성격에 안 맞고 법적 위험이 있다
#   낚시성 투자권유  "지금 사야", "폭등" 류는 요약해 실으면 투자 권유가 된다
#   콘텐츠팜·예능리캡 화자가 없어 인용할 발언이 없다 (뉴스 247의 [야구여왕2] 등)
#   편향 논평 채널   그 논조를 사이트가 그대로 뒤집어쓴다
BAD_TITLE = re.compile(
    r"승부예측|배팅|베팅|적중률|토토|무료픽|분석\.|국야분석|먹튀"
    r"|폭등|떡상|떡락|지금 사야|무조건|반드시 오른|이렇게 하세요|이것만"
    r"|탈출해야|폭발 시나리오|불장|신호 포착|\[야구여왕")
BAD_CHANNEL = re.compile(
    r"Why Times|스포차|스작|페드로|대단부자|신신 ?TV|24H"
    r"|뉴스 ?247|한국시사TV|뉴스브리핑TV|누리이슈TV")

# 영어권 낚시성 제목. 실측에서 "TOP Economist ISSUES URGENT RECESSION WARNING"이
# 한국어 필터를 그대로 통과했다.
BAD_TITLE_EN = re.compile(
    r"SHOCKING|URGENT|you won'?t believe|MUST WATCH|EXPOSED|DESTROY|INSANE"
    r"|WARNING|BREAKING|GOES WRONG|GONE WRONG|\bSCAM\b|CRASH INCOMING"
    r"|price prediction|to the moon|buy now", re.I)
# 낚시성 제목은 대문자 단어를 연달아 쓴다. 약어(FOMC, ECB, AI)는 걸리지 않게 3개 이상만.
CAPS_RUN = re.compile(r"(?:\b[A-Z]{3,}\b[^A-Za-z]+){3,}")
EMOJI_BAIT = re.compile(r"[🚨🔥💥⚠]")

MIN_SEC, MAX_SEC = 240, 1500          # 4~25분. 길면 토큰이 급증한다.
RECENT = re.compile(r"(시간|일|주) 전")   # 최근성
RECENT_LOOSE = re.compile(r"(시간|일|주|개월) 전")   # 스타트업은 최신성이 덜 중요

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
SORT_BY_UPLOAD = "CAI%253D"


def duration_seconds(text):
    """'12:51' -> 771. 라이브·형식불명이면 None."""
    if not re.fullmatch(r"(\d+:)?\d{1,2}:\d{2}", text or ""):
        return None
    seconds = 0
    for part in (int(x) for x in text.split(":")):
        seconds = seconds * 60 + part
    return seconds


def _walk_videos(node, out):
    if isinstance(node, dict):
        if "videoRenderer" in node:
            v = node["videoRenderer"]
            runs = lambda key: "".join(
                r.get("text", "") for r in v.get(key, {}).get("runs", []))
            out.append({
                "id": v.get("videoId"),
                "title": runs("title"),
                "channel": runs("ownerText"),
                "length": v.get("lengthText", {}).get("simpleText", ""),
                "published": v.get("publishedTimeText", {}).get("simpleText", ""),
            })
        for value in node.values():
            _walk_videos(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_videos(item, out)


def search_youtube(query, timeout=30):
    url = ("https://www.youtube.com/results?search_query="
           + urllib.parse.quote(query) + "&sp=" + SORT_BY_UPLOAD)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", raw)
    if not m:
        raise RuntimeError(
            "유튜브 검색결과에서 ytInitialData를 찾지 못했습니다. "
            "유튜브가 페이지 구조를 바꿨을 수 있습니다.")
    found = []
    _walk_videos(json.loads(m.group(1)), found)
    return found


def keep(video, loose_recency):
    """품질·길이·최신성 필터. 남길 값이면 True."""
    if not video["id"]:
        return False
    seconds = duration_seconds(video["length"])
    if seconds is None or not (MIN_SEC <= seconds <= MAX_SEC):
        return False
    pattern = RECENT_LOOSE if loose_recency else RECENT
    if not pattern.search(video["published"]):
        return False
    title = video["title"]
    if BAD_TITLE.search(title) or BAD_CHANNEL.search(video["channel"]):
        return False
    if BAD_TITLE_EN.search(title) or CAPS_RUN.search(title) or EMOJI_BAIT.search(title):
        return False
    return True


def collect(categories, per_category=6):
    result = {}
    for cat in categories:
        loose = cat == "스타트업"
        seen, rows = set(), []
        dropped = 0
        for query in QUERIES[cat] + EN_QUERIES.get(cat, []):
            try:
                videos = search_youtube(query)
            except Exception as e:
                print(f"  [{cat}] '{query}' 검색 실패: {e}")
                continue
            for v in videos:
                if v["id"] in seen:
                    continue
                seen.add(v["id"])
                if keep(v, loose):
                    rows.append(v)
                else:
                    dropped += 1
        result[cat] = rows[:per_category]
        print(f"  {cat}: 후보 {len(result[cat])}개 (필터로 제외 {dropped}개)")
    return result


def print_table(data):
    print()
    n = 0
    index = {}
    for cat, rows in data.items():
        print(f"── {cat} " + "─" * (74 - len(cat)))
        if not rows:
            print("   쓸 만한 후보가 없습니다. QUERIES를 손보거나 직접 링크를 찾으세요.")
        for v in rows:
            n += 1
            index[str(n)] = v | {"category": cat}
            print(f"  {n:>2}. {v['length']:>6} {v['published']:>8}  "
                  f"{v['channel'][:18]:18} {v['title'][:52]}")
        print()
    return index


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in argv[1:] if not a.startswith("--")]
    json_only = "--json" in argv

    bad = [a for a in args if a not in QUERIES]
    if bad:
        sys.exit(f"모르는 카테고리: {', '.join(bad)}\n"
                 f"가능한 값: {', '.join(QUERIES)}")
    categories = args or list(QUERIES)

    if not json_only:
        print(f"{len(categories)}개 카테고리 검색 중...")
    data = collect(categories)
    index = print_table(data) if not json_only else {
        str(i + 1): v | {"category": cat}
        for i, (cat, rows) in enumerate(data.items()) for v in rows}

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    if json_only:
        print(json.dumps(index, ensure_ascii=False, indent=1))
        return 0

    print(f"저장: {CACHE}")
    print("초안을 만들려면 링크를 draft.py에 넘기세요. 여러 개를 한 번에 넘길 수 있습니다:")
    if index:
        sample = list(index.values())[0]["id"]
        print(f"  py -3 draft.py https://youtu.be/{sample}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
