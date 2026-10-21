# -*- coding: utf-8 -*-
"""Polymarket 시장 목록 자동 관리 → data/markets.json (2026-10-20).

    py -3 markets.py              목록 갱신 (새 시장 추가 + 끝난 시장 결과 기록)
    py -3 markets.py --dry        저장하지 않고 무엇을 할지만 출력
    py -3 markets.py --backfill 10   최근 8일 안에 결과가 난 실제 시장으로 '결과' 목록 채우기

한국 IP에서는 Polymarket API가 막혀(451) 있다. 이 스크립트는 GitHub Actions(미국)
에서 돈다. 로컬에서 시험할 때는 환경변수 PM_PROXY 에 Factory Signal의
/api/proxy-polymarket?url= 주소를 넣으면 그쪽을 거친다.

data/markets.json
  { "updatedAt": ..., "markets": [ {id, q, en, cat, event, endDate, addedAt,
      last, status: "live"|"resolved", outcome: "yes"|"no", resolvedAt, final} ] }
  - last: 이 스크립트가 마지막으로 본 '예' 확률(0~100). 끝나면 final 로 굳는다
    (결과가 나면 Polymarket 가격이 0/1로 바뀌어 마감 직전 확률이 사라지므로).
  - 웹의 실시간 확률은 api/markets.js 가 따로 가져온다. 이 파일은 '어떤 질문을
    보여 줄지'와 '결과 기록'만 맡는다.

질문 고르기 — 운영 원칙(2026-10-20, 사용자): "다 가져오지 말고 진짜 핫한 것 10개 정도만".
전부 나열하면 Polymarket 복제(=예전 signalvip)와 다를 게 없다. 그래서 진행 중 질문은
LIVE_MAX개로 고정하고, 24시간 거래량이 큰 순서로 고른다. 결과가 뻔한(확률 8% 미만·92%
초과) 시장은 빼고, 한 사건(event)에서는 1개만, 한 분야가 독차지하지 않게 분야당 CAT_MAX개.
번역은 Gemini 한 번 호출로 새 질문만 한다. 실패하면 이번에는 추가하지 않는다.
"""
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

import gemini

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "markets.json")
GAMMA = "https://gamma-api.polymarket.com"
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

LIVE_MAX = 10                 # 동시에 보여 줄 진행 중 질문 수
CAT_MAX = 4                   # 그중 한 분야 최대
ADD_PER_RUN = LIVE_MAX        # 한 번에 새로 넣는 최대 수 (번역 1회 분량)
MIN_VOL24 = 50000             # 24시간 거래량(달러) 하한 — '핫한' 것만
MAX_DAYS = 45                 # 결과가 너무 먼 시장 제외 (결과가 자주 나와야 프로필이 쌓인다)
KEEP_RESOLVED = 200

# 이런 시장은 빼거나(SKIP) 분야를 정한다(태그 라벨 기준, 앞에서부터 먼저 맞는 것).
SKIP_TAGS = {"Tweet Markets", "Mention Markets", "Weather", "Daily Temperature",
             "Highest temperature", "Tennis", "Up or Down", "5M", "15M", "Hourly",
             # 2026-10-21: 국내 관심 낮은 e스포츠 (LoL은 유지)
             "counter strike 2", "Counter Strike 2", "Counter-Strike", "CS2", "Dota 2", "Valorant"}
CAT_TAGS = [
    ("코인", {"Crypto", "Crypto Prices", "Bitcoin", "Ethereum", "Solana", "XRP"}),
    ("경제", {"Economy", "Fed", "Fed Rates", "fomc", "Finance", "Oil", "Global Rates",
              "Macro Indicators", "Economic Policy", "Stocks", "Inflation", "Tariffs"}),
    ("스포츠", {"Sports", "Esports", "Soccer", "NBA", "NFL", "MLB", "league of legends"}),
    ("테크·문화", {"Tech", "AI", "Anthropic", "OpenAI", "Culture", "Movies", "Music",
                 "GTA VI", "Science", "Apple"}),
    ("정치·세계", {"Politics", "Geopolitics", "Elections", "World", "Global Elections",
                 "Middle East", "Ukraine", "Iran", "South Korea", "North Korea", "China"}),
]
# 한국 독자가 관심 가질 만한 것은 거래량이 적어도 우선한다.
BOOST_TAGS = {"South Korea", "North Korea", "Esports", "league of legends", "Bitcoin", "Fed"}


def _get(path, **params):
    url = f"{GAMMA}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    proxy = os.environ.get("PM_PROXY")
    if proxy:   # 로컬 시험용: 프록시는 url= 뒤 나머지 쿼리를 그대로 넘긴다
        url = proxy + f"{GAMMA}{path}" + (("&" + urllib.parse.urlencode(params)) if params else "")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _jl(s, default=None):
    try:
        return json.loads(s) if isinstance(s, str) else (s if s is not None else default)
    except ValueError:
        return default


def yes_price(m):
    p = _jl(m.get("outcomePrices"), [])
    try:
        return float(p[0])
    except (IndexError, TypeError, ValueError):
        return None


def is_binary(m):
    return [o.lower() for o in _jl(m.get("outcomes"), [])] == ["yes", "no"]


def _words(title):
    import re
    stop = {"the", "a", "of", "in", "on", "by", "will", "be", "x", "vs", "and", "to", "2026", "2027"}
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in stop and len(w) > 1}


def similar(a, b):
    """사건 제목이 거의 같은 주제인지 (예: 'US x Iran ceasefire…'와 'US-Iran ceasefire…')."""
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def as_question(m, e):
    """예/아니오 시장이면 그 질문, 두 팀 경기의 '최종 승자' 시장이면 'Will A beat B?'.
    세트별(Game 1 Winner)·핸디캡·합계 같은 부가 시장은 None."""
    outs = _jl(m.get("outcomes"), [])
    if [o.lower() for o in outs] == ["yes", "no"]:
        return m.get("question", "")
    q = (m.get("question") or "").strip()
    if len(outs) == 2 and q == (e.get("title") or "").strip() and " vs" in q:
        return f"Will {outs[0]} beat {outs[1]}? ({q})"
    return None


def category(labels):
    for cat, tags in CAT_TAGS:
        if labels & tags:
            return cat
    return None


def candidates(now):
    """진행 중 사건들에서 질문 후보를 뽑는다. [(점수, 후보dict)]"""
    events = []
    for offset in (0, 100, 200):
        events += _get("/events", active="true", closed="false", order="volume24hr",
                       ascending="false", limit=100, offset=offset)
    for slug in ("crypto", "economy", "fed-rates", "south-korea", "esports", "ai"):
        try:
            events += _get("/events", active="true", closed="false", tag_slug=slug,
                           order="volume24hr", ascending="false", limit=30)
        except Exception as e:  # 태그 하나 실패해도 나머지로 진행
            print(f"  태그 {slug} 실패: {e}")
    seen, out = set(), []
    for e in events:
        if e.get("id") in seen:
            continue
        seen.add(e.get("id"))
        labels = {t.get("label", "") for t in e.get("tags") or []}
        if labels & SKIP_TAGS:
            continue
        cat = category(labels)
        if not cat:
            continue
        best = None
        for m in e.get("markets") or []:
            if m.get("closed") or not m.get("active"):
                continue
            en = as_question(m, e)
            if not en:
                continue
            p = yes_price(m)
            if p is None or not (0.08 <= p <= 0.92):
                continue
            end = (m.get("endDate") or e.get("endDate") or "")
            try:
                end_dt = datetime.datetime.fromisoformat(end.replace("Z", "+00:00"))
            except ValueError:
                continue
            days = (end_dt - now).total_seconds() / 86400
            if days < 0.2 or days > MAX_DAYS:
                continue
            vol = float(m.get("volume24hr") or 0)
            boosted = bool(labels & BOOST_TAGS)
            if vol < (MIN_VOL24 / 5 if boosted else MIN_VOL24):
                continue
            # 점수: 거래량(핫함)이 기본. 한국 관심사는 가산, 결과가 팽팽할수록 약간 가산.
            score = vol * (1.2 - abs(p - 0.5) / 2) * (2 if boosted else 1)
            if not best or score > best[0]:
                best = (score, {
                    "id": str(m["id"]), "en": en,
                    "group": m.get("groupItemTitle") or "", "eventTitle": e.get("title", ""),
                    "cat": cat, "event": e.get("slug", ""), "endDate": end[:19] + "Z",
                    "last": round(p * 1000) / 10,
                })
        if best:
            out.append(best)
    out.sort(key=lambda x: -x[0])
    return [c for _, c in out]


BACKFILL_TAGS = ("politics", "geopolitics", "economy", "fed-rates", "crypto", "tech", "ai",
                 "south-korea", "league-of-legends", "soccer", "nba", "mlb")
CLOB = "https://clob.polymarket.com"


def _ts(s):
    s = (s or "").replace(" ", "T").replace("+00", "+00:00").replace("Z", "+00:00")
    if s.endswith("+00:00:00"):
        s = s[:-3]
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


def price_before(token, when):
    """when 시각 직전의 '첫째 결과' 가격(0~1). 이력이 없으면 None."""
    url_base = f"{CLOB}/prices-history"
    params = dict(market=token, startTs=int(when.timestamp()) - 12 * 3600,
                  endTs=int(when.timestamp()), fidelity=10)
    proxy = os.environ.get("PM_PROXY")
    url = (proxy + url_base + "&" if proxy else url_base + "?") + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        hist = json.loads(r.read().decode("utf-8")).get("history") or []
    return float(hist[-1]["p"]) if hist else None


def recent_resolved(now, n, have):
    cutoff = now - datetime.timedelta(days=8)
    events, seen = [], set()
    for slug in BACKFILL_TAGS:
        try:
            events += _get("/events", closed="true", tag_slug=slug, order="volume", ascending="false",
                           limit=60, end_date_min=(now - datetime.timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        except Exception as e:
            print(f"  태그 {slug} 실패: {e}")
    out = []
    for e in events:
        if e.get("id") in seen:
            continue
        seen.add(e.get("id"))
        labels = {t.get("label", "") for t in e.get("tags") or []}
        cat = category(labels)
        if not cat or labels & SKIP_TAGS:
            continue
        best = None
        for m in e.get("markets") or []:
            closed_at = _ts(m.get("closedTime"))
            if not m.get("closed") or not closed_at or closed_at < cutoff or str(m["id"]) in have:
                continue
            en = as_question(m, e)
            p_end = yes_price(m)
            if not en or p_end is None or 0.01 < p_end < 0.99:
                continue            # 결과가 0/1로 확정된 것만
            vol = float(m.get("volumeNum") or m.get("volume") or 0)
            if not best or vol > best[0]:
                best = (vol, m, en, closed_at, p_end)
        if not best:
            continue
        vol, m, en, closed_at, p_end = best
        score = vol * (3 if labels & BOOST_TAGS else 1)
        out.append((score, {"m": m, "en": en, "cat": cat, "e": e, "closed_at": closed_at, "yes": p_end >= 0.99}))
    out.sort(key=lambda x: -x[0])

    picks, per_cat = [], {}
    for vol, c in out:
        if len(picks) >= n:
            break
        if per_cat.get(c["cat"], 0) >= 3 or any(similar(c["e"].get("title", ""), x["e"].get("title", "")) for x in picks):
            continue
        m = c["m"]
        start = _ts(m.get("gameStartTime"))
        # 경기는 시작 직전, 그 밖(지표 발표·가격 등)은 마감 하루 전 — 결과를 모를 때의 기대치.
        when = start - datetime.timedelta(minutes=5) if start and start < c["closed_at"] else c["closed_at"] - datetime.timedelta(hours=24)
        try:
            token = _jl(m.get("clobTokenIds"), [])[0]
            p = price_before(token, when)
        except Exception as ex:
            print(f"  가격 이력 실패 {m['id']}: {ex}")
            continue
        if p is None or not (0.05 <= p <= 0.95):
            continue                # 결과가 뻔했던 것은 보여 줄 가치가 적다
        c.update(final=round(p * 1000) / 10)
        picks.append(c)
        per_cat[c["cat"]] = per_cat.get(c["cat"], 0) + 1
    return picks


TRANSLATE_PROMPT = """아래는 해외 예측시장의 예/아니오 질문들이다. 한국 독자용 질문으로 옮겨라.
규칙:
- 자연스러운 한국어 의문문 한 문장, 물음표로 끝낸다. 60자 이내.
- 날짜·숫자·기준은 빠짐없이 정확히 옮긴다 (예: "10월 회의에서", "11만 달러 이상").
  달러 금액은 "11만 달러"처럼, 기준금리 bp는 "0.25%p"처럼 쓴다.
- 인물·팀·국가는 한국 언론에서 쓰는 표기로 쓴다 (Trump→트럼프, Fed→연준).
- 베팅·돈을 거는 표현은 쓰지 않는다. 질문 내용만 옮긴다.
- 원문에 없는 내용을 더하지 않는다.
- "Will A beat B? (경기명)" 꼴은 "A가 B를 이길까?"로 옮기고, 대회명이 있으면 앞에 붙인다
  (예: "롤드컵 플레이인: T1이 G2를 이길까?"). BO5 같은 표기는 빼도 된다.
입력(JSON 목록): 각 항목의 en(질문), group(선택지 이름), eventTitle(사건 제목)을 참고한다.
출력: {"items": [{"id": "...", "q": "한국어 질문"}]} — 입력의 모든 id에 대해."""


def translate(cfg, items):
    payload = {
        "contents": [{"parts": [{"text": TRANSLATE_PROMPT + "\n\n" + json.dumps(
            [{k: it[k] for k in ("id", "en", "group", "eventTitle")} for it in items],
            ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    data, _ = gemini.request(cfg, payload, timeout=120)
    out = {}
    for x in data.get("items", []):
        q = str(x.get("q", "")).strip()
        if 6 <= len(q) <= 80 and q.endswith("?"):
            out[str(x.get("id"))] = q
    return out


def load():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"updatedAt": "", "markets": []}


def refresh_live(markets, now):
    """진행 중인 질문의 최신 확률과 종료·결과를 기록한다."""
    for m in markets:
        if m.get("status") != "live":
            continue
        try:
            g = _get(f"/markets/{m['id']}")
        except Exception as e:
            print(f"  {m['id']} 조회 실패: {e}")
            continue
        p = yes_price(g)
        if not g.get("closed"):
            if p is not None:
                m["last"] = round(p * 1000) / 10
            continue
        # 끝남. 가격이 1/0으로 굳었으면 결과 확정, 아니면 판정 대기(다음 실행에서 다시 본다).
        if p is not None and p >= 0.99:
            outcome = "yes"
        elif p is not None and p <= 0.01:
            outcome = "no"
        else:
            m["pending"] = True
            continue
        m.pop("pending", None)
        m.update(status="resolved", outcome=outcome, final=m.get("last"),
                 resolvedAt=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        print(f"  결과: {m['q']} → {'예' if outcome == 'yes' else '아니오'} (마지막 확률 {m.get('last')}%)")


def main():
    dry = "--dry" in sys.argv
    backfill = int(sys.argv[sys.argv.index("--backfill") + 1]) if "--backfill" in sys.argv else 0
    limit = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else ADD_PER_RUN
    now = datetime.datetime.now(datetime.timezone.utc)
    data = load()
    markets = data["markets"]
    refresh_live(markets, now)

    live = [m for m in markets if m.get("status") == "live"]
    have = {m["id"] for m in markets}
    have_events = {m.get("event") for m in live}
    have_titles = [m.get("eventTitle", "") for m in live]
    per_cat = {}
    for m in live:
        per_cat[m["cat"]] = per_cat.get(m["cat"], 0) + 1
    room = min(limit, LIVE_MAX - len(live))
    picks = []
    for c in (candidates(now) if room > 0 else []):
        if len(picks) >= room:
            break
        if c["id"] in have or c["event"] in have_events or per_cat.get(c["cat"], 0) >= CAT_MAX:
            continue
        if any(similar(c["eventTitle"], t) for t in have_titles):   # 같은 주제 두 번 금지
            continue
        picks.append(c)
        have_events.add(c["event"])
        have_titles.append(c["eventTitle"])
        per_cat[c["cat"]] = per_cat.get(c["cat"], 0) + 1
    print(f"진행 중 {len(live)}개, 빈자리 {max(room, 0)}개, 새 후보 {len(picks)}개")

    if picks and not dry:
        try:
            cfg_path = os.path.join(HERE, "config.json")
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            ko = translate(cfg, picks)
        except Exception as e:
            print(f"  번역 실패 — 이번에는 새 질문을 넣지 않습니다: {str(e)[:300]}")
            ko = {}
        for c in picks:
            if c["id"] not in ko:
                continue
            markets.append({
                "id": c["id"], "q": ko[c["id"]], "en": c["en"], "cat": c["cat"],
                "event": c["event"], "eventTitle": c["eventTitle"], "endDate": c["endDate"], "last": c["last"],
                "addedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "live",
            })
            print(f"  추가 [{c['cat']}] {ko[c['id']]}  ({c['last']}%)")
    elif dry:
        for c in picks:
            print(f"  후보 [{c['cat']}] {c['en']}  ({c['last']}%, ~{c['endDate'][:10]})")

    if backfill:
        done = recent_resolved(now, backfill, {m["id"] for m in markets})
        for c in done:
            print(f"  최근 결과 후보 [{c['cat']}] {c['en']} → {'예' if c['yes'] else '아니오'} (마감 전 {c['final']}%)")
        if done and not dry:
            items = [{"id": str(c["m"]["id"]), "en": c["en"], "group": c["m"].get("groupItemTitle") or "",
                      "eventTitle": c["e"].get("title", "")} for c in done]
            try:
                with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
                    ko = translate(json.load(f), items)
            except Exception as ex:
                print(f"  번역 실패: {str(ex)[:300]}")
                ko = {}
            for c in done:
                mid = str(c["m"]["id"])
                if mid not in ko:
                    continue
                markets.append({
                    "id": mid, "q": ko[mid], "en": c["en"], "cat": c["cat"], "event": c["e"].get("slug", ""),
                    "eventTitle": c["e"].get("title", ""), "endDate": (c["m"].get("endDate") or "")[:19] + "Z",
                    "last": c["final"], "addedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "resolved",
                    "outcome": "yes" if c["yes"] else "no", "final": c["final"], "backfill": True,
                    "resolvedAt": c["closed_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

    # 결과 난 것은 최근 것만 남긴다.
    resolved = sorted((m for m in markets if m.get("status") == "resolved"),
                      key=lambda m: m.get("resolvedAt", ""), reverse=True)[:KEEP_RESOLVED]
    data["markets"] = [m for m in markets if m.get("status") == "live"] + resolved
    data["updatedAt"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not dry:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
