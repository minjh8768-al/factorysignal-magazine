# -*- coding: utf-8 -*-
"""예측 기사 초안 (2026-10-21). 첫 화면 예측 질문(data/markets.json) 하나당 기사 두 종류:

  preview  진행 중인 질문 — "왜 지금 이 확률인가"
  result   결과가 난 질문 — "시장은 몇 %로 봤고, 결과는 이랬다"

    py -3 market_article.py            쓸 차례인 질문 최대 MAX_PER_RUN개를 _drafts/ 에 초안으로
    py -3 market_article.py --dry      무엇을 쓸지만 출력

초안은 GitHub Actions 결과물(drafts-<번호>)로 남고, 관리자 페이지 '승인 대기'에서 확인·수정 후
발행한다(사람 승인 없이 자동 발행하지 않는다). 이미 초안을 만든 질문은 data/drafted.json 에
적어 두어 다시 쓰지 않는다 (markets.json 은 4시간마다 다른 작업이 고치므로 따로 둔다).

원칙: 숫자(확률·날짜·결과)는 이 파일이 넣어 주는 값만 쓰게 한다. 근거는 Google News 헤드라인과
Polymarket의 판정 기준 설명. 매수·매도·베팅 권유 금지, Polymarket 링크 없음.
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.request

import article
import commons
import gemini
import gnews
import markets
import pexels

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
DRAFTS = os.path.join(HERE, "..", "_drafts")
ARTICLES = os.path.join(HERE, "..", "articles")
DRAFTED = os.path.join(DATA, "drafted.json")
MAX_PER_RUN = 4
RESULT_WITHIN_DAYS = 10

# 예측 분야 → 기사 분류(article.CATEGORIES). 첫 화면은 article.OLD_TO_MKT 로 다시 묶어 보여 준다.
CAT_TO_ARTICLE = {"경제": "경제", "코인": "암호화폐", "스포츠": "스포츠", "테크·문화": "스타트업"}

PROMPT = """너는 한국 독자용 예측 매체 'Factory Magazine'의 기자다. 해외 예측시장(Polymarket)의 질문 하나를 두고 기사를 쓴다.

[질문] {q}
[원문 질문] {en}
[분야] {cat}
[판정 기준(원문)] {rules}
{facts}
[관련 최신 보도 헤드라인 — 영어권]
{news_en}
[관련 최신 보도 헤드라인 — 한국]
{news_ko}

{task}

공통 규칙:
- 숫자(확률·날짜·결과)는 위에 준 값만 쓴다. 다른 통계·수치를 지어내지 않는다.
- 헤드라인과 일반 상식으로 확인되지 않는 사실을 단정하지 않는다. 불확실하면 "~로 알려졌다", "~라는 관측이 있다"처럼 쓴다.
- 사기·팔기·돈 걸기 같은 권유, 베팅·도박 표현, Polymarket 가입·이용 안내는 쓰지 않는다. 확률은 '시장 참가자들의 판단'으로 소개한다.
- 본문은 공백 포함 1,000~1,600자. 기사체(~다)로 쓰되 맨 앞 핵심 요약 3줄만 해요체.
- 구조: <ul> 핵심 요약 3줄(<li> 각 한 문장) → 도입 단락 1개 → <h2> 소제목 2~3개, 각 단락 1~2개.
- 허용 태그: <p> <h2> <blockquote> <ul> <li> <strong>. 마크다운, <h1>, <div>, <img>, 링크, 인라인 스타일 금지.

JSON으로만 답한다:
{{"title": "제목(45자 이내, 확률 숫자를 넣으면 좋다)",
  "description": "검색·카드용 한 문장 요약(80자 이내)",
  "category": "{cat_choice}",
  "eyebrow": "{eyebrows} 중 하나",
  "slug": "영문 소문자-하이픈 (예: netanyahu-next-pm-odds)",
  "photo_subject": "질문의 주인공이 한 명의 실존 인물(정치인·선수·CEO) 또는 하나의 팀일 때만 영어 정식 이름(예: Benjamin Netanyahu, T1). 국가·정부·협정·사건·지표·가격이면 반드시 빈 문자열",
  "photo_query": "주인공이 없을 때 쓸 영어 장면 사진 검색어 2~3단어 (예: Tehran skyline, stock market screen, bitcoin coins). 경찰·군인·무기·사고 장면 금지",
  "body_html": "본문 HTML"}}"""

TASK_PREVIEW = """[할 일] '예측 기사'를 쓴다. 이 질문은 아직 결과가 나지 않았다.
- 무엇을 묻는 질문인지, 결과는 언제 정해지는지 쉽게 설명한다.
- 시장 참가자들이 '예' 가능성을 {p}%로 보는 이유를 보도 내용에 기대어 풀어 준다.
- 확률을 바꿀 수 있는 앞으로의 변수(일정·발표·경기 등)를 짚는다.
- 결론을 예측하지 않는다. 독자가 스스로 예/아니오를 고를 수 있게 근거를 정리하는 데서 끝낸다."""

TASK_RESULT = """[할 일] '결과 기사'를 쓴다. 이 질문은 결과가 났다.
- 결과: '{outcome}'. 결과가 나오기 전 시장은 '예' 가능성을 {final}%로 봤다. {upset}
- 무슨 일이 있었는지, 시장의 예상과 실제 결과를 비교한다.
- 시장이 맞혔다면 무엇을 근거로 확신했는지, 틀렸다면 무엇을 놓쳤는지 보도에 기대어 짚는다."""


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def market_detail(mid):
    try:
        return markets._get(f"/markets/{mid}")
    except Exception:
        return {}


def news_query(en):
    """'Will X beat Y? (LoL: ...)' 같은 질문을 검색어로."""
    q = re.sub(r"\(.*?\)", " ", en)
    q = re.sub(r"\b(Will|will|be|the|by|on|in|of|a|an)\b|\?", " ", q)
    return " ".join(q.split()[:8])


def headlines(query, lang):
    n, rows = gnews.search(query, lang=lang, limit=8)
    if n is None or not rows:
        return "(없음)"
    return "\n".join(f"- {t} ({s})" for t, s in rows if t)


def load_drafted():
    try:
        with open(DRAFTED, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def published_pairs():
    """이미 발행된 기사의 (질문id, 종류) — 관리자가 손으로 발행한 것도 포함."""
    out = set()
    for name in os.listdir(ARTICLES):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(ARTICLES, name), encoding="utf-8") as f:
            head = f.read(3000)
        m = re.search(r'name="fs:market" content="(\d+)"', head)
        k = re.search(r'name="fs:market_kind" content="(\w+)"', head)
        if m and k:
            out.add((m.group(1), k.group(1)))
    return out


def todo(data, drafted, now):
    done = published_pairs() | {(mid, kind) for mid, kinds in drafted.items() for kind in kinds}
    jobs = []
    for m in data["markets"]:
        if m.get("status") == "resolved" and (m["id"], "result") not in done:
            when = datetime.datetime.fromisoformat((m.get("resolvedAt") or "2000-01-01T00:00:00Z").replace("Z", "+00:00"))
            if (now - when).days <= RESULT_WITHIN_DAYS:
                jobs.append((0, m, "result"))
        elif m.get("status") == "live" and (m["id"], "preview") not in done:
            jobs.append((1, m, "preview"))
    jobs.sort(key=lambda j: (j[0], j[1].get("resolvedAt") or j[1].get("addedAt") or ""), reverse=False)
    # 결과 기사는 최근 것부터
    # 결과 기사는 '이변'(시장이 50% 미만으로 본 쪽이 일어남) 먼저, 그다음 최근 것.
    def upset(m):
        side = m["final"] if m["outcome"] == "yes" else 100 - m["final"]
        return side < 50
    res = sorted([j for j in jobs if j[2] == "result"],
                 key=lambda j: (upset(j[1]), j[1].get("resolvedAt", "")), reverse=True)
    pre = [j for j in jobs if j[2] == "preview"]
    # 진행 중 질문의 예측 기사와 결과 기사를 번갈아 (첫 화면 두 구역이 고르게 채워지게)
    out = []
    for i in range(max(len(res), len(pre))):
        out += [j for j in (pre[i] if i < len(pre) else None, res[i] if i < len(res) else None) if j]
    return [(m, k) for _, m, k in out]


def write(cfg, m, kind, today):
    detail = market_detail(m["id"])
    rules = (detail.get("description") or "").strip().replace("\n", " ")[:900] or "(없음)"
    query = news_query(m["en"])
    cat = m["cat"]
    if cat == "정치·세계":
        cat_choice, art_cats = "정치 또는 세계 중 하나 (한국·미국 국내정치면 정치, 국제 이슈면 세계)", ("정치", "세계")
    else:
        cat_choice, art_cats = CAT_TO_ARTICLE[cat], (CAT_TO_ARTICLE[cat],)
    eyebrows = " / ".join(sorted({e for c in art_cats for e in article.EYEBROWS[c]}))
    end = (m.get("endDate") or "")[:10]
    if kind == "preview":
        facts = f"[현재 시장 확률] '예' {m['last']}%\n[결과가 정해지는 시한] {end}"
        task = TASK_PREVIEW.format(p=m["last"])
    else:
        side = m["final"] if m["outcome"] == "yes" else round(100 - m["final"], 1)
        upset = (f"시장이 {side}%로 낮게 본 쪽이 일어난 '이변'이다." if side < 50 else
                 f"시장이 {side}%로 높게 본 쪽이 그대로 일어났다.")
        facts = f"[결과] {'예' if m['outcome'] == 'yes' else '아니오'}\n[결과 직전 시장 확률] '예' {m['final']}%\n[결과 확정] {(m.get('resolvedAt') or '')[:10]}"
        task = TASK_RESULT.format(outcome="예" if m["outcome"] == "yes" else "아니오", final=m["final"], upset=upset)
    prompt = PROMPT.format(q=m["q"], en=m["en"], cat=cat, rules=rules, facts=facts,
                           news_en=headlines(query, "en"), news_ko=headlines(m["q"].rstrip("?"), "ko"),
                           task=task, cat_choice=cat_choice, eyebrows=eyebrows)
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}}
    fields, _ = gemini.request(cfg, payload, timeout=300)

    category = fields.get("category", "")
    if category not in art_cats:
        category = art_cats[-1]
    fields["category"] = category
    fields["slug"] = article.clean_slug(fields.get("slug") or f"market-{m['id']}-{kind}")
    body = article.tidy_body(article.validate_body(fields["body_html"]))
    read = max(2, round(len(re.sub(r"<[^>]+>", "", body)) / 500))

    subject = (fields.get("photo_subject") or "").strip()
    photo = commons.search(subject) if subject else None
    if not photo:
        q = (fields.get("photo_query") or "").strip() or pexels.query_for(fields.get("title", ""), fields.get("eyebrow", ""))
        photo = pexels.photo(cfg, q, pexels.pick_index(fields["slug"], 8))
    return render(fields, body, read, photo, m, kind), fields["slug"]


def render(fields, body, read, photo, m, kind):
    esc = lambda v: html.escape(str(v), quote=True)
    category = article.validate_category(fields["category"])
    eyebrow = article.normalize_eyebrow(category, fields.get("eyebrow", ""))
    photo_tags = ""
    if photo and photo.get("url"):
        photo_tags += f'<meta name="fs:photo" content="{esc(photo["url"])}" />\n'
        if photo.get("by"):
            photo_tags += f'<meta name="fs:photo_by" content="{esc(photo["by"])}" />\n'
        for key in ("license", "src"):
            if photo.get(key):
                photo_tags += f'<meta name="fs:photo_{key}" content="{esc(photo[key])}" />\n'
    label = "예측 기사" if kind == "preview" else "결과 기사"
    note = ("해외 예측시장(Polymarket) 참가자들이 매긴 확률과 공개 보도를 바탕으로 작성한 예측 기사입니다. "
            "본문의 확률은 기사 작성 시점 값이며, 위 카드에서 지금 확률을 보고 직접 예측해 볼 수 있습니다."
            if kind == "preview" else
            "해외 예측시장(Polymarket)이 결과 전에 매긴 확률과 실제 결과, 공개 보도를 바탕으로 작성한 결과 기사입니다.")
    nav = article._NAV
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{esc(fields['title'])}{article.TITLE_SUFFIX}</title>
<meta name="description" content="{esc(fields['description'])}" />
<meta name="fs:category" content="{esc(category)}" />
<meta name="fs:eyebrow" content="{esc(eyebrow)}" />
<meta name="fs:read" content="{read}" />
<meta name="fs:market" content="{esc(m['id'])}" />
<meta name="fs:market_kind" content="{kind}" />
{photo_tags}<link rel="stylesheet" href="../css/style.css" />
</head>
<body>

{nav}

<header class="article-hero">
  <div class="wrap">
    <a href="index.html" class="back-link">← 첫 화면으로</a>
    <span class="section-eyebrow">{label} · {esc(eyebrow)}</span>
    <h1>{esc(fields['title'])}</h1>
    <div class="article-meta"><span class="byline-avatar">FS</span><span class="byline-name">{article.BYLINE}</span> · <span>{read}분 읽기</span></div>
  </div>
</header>

<article class="article-content">

  <div class="mk-article-market" data-market="{esc(m['id'])}"></div>
  <p class="source-note">{note}</p>

{body}

  <div class="disclaimer">
    이 기사는 정보 제공용입니다. 예측시장 확률은 참가자들의 판단을 숫자로 옮긴 것이며 사실이나 결과를 보장하지 않습니다. 투자·베팅 권유가 아닙니다.
  </div>

</article>

{article._FOOTER}

<script src="../js/main.js"></script>
</body>
</html>
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    dry = "--dry" in sys.argv
    now = datetime.datetime.now(datetime.timezone.utc)
    today = (now + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")
    with open(os.path.join(DATA, "markets.json"), encoding="utf-8") as f:
        data = json.load(f)
    drafted = load_drafted()
    jobs = todo(data, drafted, now)
    print(f"쓸 차례 {len(jobs)}건 — 이번에 최대 {MAX_PER_RUN}건")
    jobs = jobs[:MAX_PER_RUN]
    for m, kind in jobs:
        print(f"  [{kind}] {m['q']}")
    if dry or not jobs:
        return 0
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    os.makedirs(DRAFTS, exist_ok=True)
    made = 0
    for m, kind in jobs:
        try:
            page, slug = write(cfg, m, kind, today)
        except Exception as e:
            print(f"  실패 [{kind}] {m['q']}: {str(e)[:300]}")
            if "하루 요청 한도" in str(e):
                break
            continue
        # 같은 이름의 기사·초안이 이미 있으면 질문 id를 붙여 겹치지 않게
        if os.path.exists(os.path.join(ARTICLES, slug + ".html")) or any(
                n.endswith(f"-{slug}.html") for n in os.listdir(DRAFTS)):
            slug = f"{slug}-{m['id']}"
        name = f"{today}-{slug}.html"
        with open(os.path.join(DRAFTS, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(page)
        drafted.setdefault(m["id"], {})[kind] = today
        made += 1
        print(f"  초안 {name}")
    with open(DRAFTED, "w", encoding="utf-8", newline="\n") as f:
        json.dump(drafted, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"초안 {made}/{len(jobs)}편")
    return 0


if __name__ == "__main__":
    sys.exit(main())
