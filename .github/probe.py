# -*- coding: utf-8 -*-
"""GitHub 러너에서 외부 의존성이 살아 있는지 잰다. 키가 필요 없는 것만 본다.

왜 필요한가
    파이프라인을 PC 예약작업에서 GitHub Actions 로 옮기기 전에, 데이터센터 IP
    에서도 같은 소스가 열리는지 확인해야 한다. 특히 유튜브 검색은 HTML 스크래핑
    이라 클라우드 IP 를 막거나 동의 페이지를 내주는 일이 잦다. 그게 막히면 아침
    영상 배치가 통째로 안 돌아간다.

    결과를 파일로 남기고 워크플로가 커밋한다 — 로컬에서 git pull 로 바로 읽는다.
"""
import json
import os
import socket
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
OUT = []


def log(line):
    print(line, flush=True)
    OUT.append(line)


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def probe(name, fn):
    t0 = time.time()
    try:
        detail = fn()
        log(f"OK    {name:26} {time.time()-t0:5.1f}s  {detail}")
        return True
    except Exception as e:
        log(f"FAIL  {name:26} {time.time()-t0:5.1f}s  {type(e).__name__}: {e}"[:200])
        return False


def yt_search():
    """가장 중요한 항목. collect.py 의 실제 경로를 그대로 쓴다."""
    import collect
    rows = collect.search_youtube("국회 여야 쟁점")
    if not rows:
        raise RuntimeError("결과 0건")
    return f"{len(rows)}건  첫 항목: {rows[0]['channel'][:14]} / {rows[0]['title'][:28]}"


def yt_oembed():
    import youtube
    info = youtube.fetch_meta("dQw4w9WgXcQ")
    return f"{info.get('author_name')}"


def yahoo():
    import market
    stamps, values = market.yahoo("^KS11")
    return f"KOSPI {len(values)}일  최근 {values[-1]:,.2f}"


def coingecko():
    import market
    stamps, values = market.coingecko(days=7)
    return f"BTC {len(values)}일  최근 {values[-1]:,.0f}원"


def gnews():
    status, body = get("https://news.google.com/rss/search?q=%EA%B2%BD%EC%A0%9C"
                       "&hl=ko&gl=KR&ceid=KR:ko")
    n = body.count(b"<item")
    if not n:
        raise RuntimeError("item 0건")
    return f"{n}건"


def telegram_reach():
    """토큰 없이 도달만 확인 — 401 이 오면 네트워크는 열린 것이다."""
    try:
        get("https://api.telegram.org/bot0:0/getMe", timeout=15)
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} (도달 가능)"
    return "200"


def main():
    log("=" * 78)
    log(f"러너 조사  {time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    log(f"python {sys.version.split()[0]}  host {socket.gethostname()}")
    try:
        _, body = get("https://api.ipify.org?format=json", timeout=15)
        log(f"공인 IP   {json.loads(body).get('ip')}")
    except Exception as e:
        log(f"공인 IP   확인 실패 {e}")
    log("-" * 78)

    results = {
        "youtube_search": probe("유튜브 검색(스크래핑)", yt_search),
        "youtube_oembed": probe("유튜브 oEmbed", yt_oembed),
        "yahoo": probe("Yahoo Finance", yahoo),
        "coingecko": probe("CoinGecko", coingecko),
        "google_news": probe("Google News RSS", gnews),
        "telegram": probe("Telegram 도달", telegram_reach),
    }

    log("-" * 78)
    ok = sum(1 for v in results.values() if v)
    log(f"통과 {ok}/{len(results)}")
    if not results["youtube_search"]:
        log("")
        log("!! 유튜브 검색이 막혔다. 아침 영상 배치는 러너에서 돌 수 없다.")
        log("   분석 기사(시장 데이터 기반)는 영향 없다.")

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "_probe_result.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n기록: {path}")
    return 0        # 조사 자체는 항상 성공으로 끝낸다(결과는 파일에 있다)


if __name__ == "__main__":
    sys.exit(main())
