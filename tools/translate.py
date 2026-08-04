# -*- coding: utf-8 -*-
"""발행된 한국어 기사 -> 영어판 (`<slug>-en.html`).

    py -3 translate.py                       영어판이 없는 기사 전부
    py -3 translate.py fomc criminal         slug 일부로 지정
    py -3 translate.py --force fomc          이미 있어도 다시 만든다

영상을 다시 읽히지 않는다. 이미 있는 한국어 본문만 번역하므로 편당 약 5천 토큰이면
끝난다(초안 생성은 11만 토큰). 그래서 6편을 한 번에 돌려도 부담이 없다.

인용문은 한국어 원문을 blockquote에 그대로 두고 바로 아래 영어 번역을 붙인다.
남의 발언이라 원문을 지우면 검증할 수 없게 된다.
"""
import glob
import html
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import article
import gemini

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARTICLES = os.path.join(ROOT, "articles")

MAX_PARALLEL = 3
_print_lock = threading.Lock()

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
        "eyebrow": {"type": "STRING"},
        "body_html": {"type": "STRING"},
    },
    "required": ["title", "description", "eyebrow", "body_html"],
    "propertyOrdering": ["title", "description", "eyebrow", "body_html"],
}

PROMPT = """You are translating a Korean news article into English for Factory Magazine.

Rules:
- Translate faithfully. Do not add facts, opinions, or context that is not in the source.
- Keep the same section structure: the same number of <h2> headings, in the same order.
- Keep every <blockquote> in the ORIGINAL KOREAN, unchanged, and add the English
  translation immediately after it as <p class="quote-tr">"..."</p>.
  The reader must be able to check the translation against the speaker's actual words.
- Do NOT create new <blockquote> elements. If the Korean has three blockquotes, the English
  has exactly three. Quoted speech that sits inline inside a <p> stays inline inside a <p>.
- Do NOT introduce any year, date or figure that is not in the Korean text. If the Korean
  says 내년, write "next year" — never guess a specific year.
- Korean names: use the standard romanisation used by English-language news
  (Lee Jae-myung, Yoon Sung-bin, Kwak Sang-eon). Give the Korean in parentheses on first
  mention only when the person is not widely known in English.
- Organisations: use the official English name (National Assembly, Democratic Party,
  Lotte Giants, Bank of Korea). Do not invent names you are unsure of.
- Keep numbers, dates and percentages exactly as they are.
- Use plain declarative news style, past tense where the Korean uses it.
- Allowed tags only: <p> <h2> <h3> <blockquote> <ul> <ol> <li> <strong> <em> <a>.
  No <div>, <script>, <style>, <img>, no inline style attributes, no markdown.

Fields:
- title: English headline. Do not translate word-for-word; write a natural English headline.
- description: one-sentence summary for search results (100-180 characters).
- eyebrow: the same 2-3 word English label as the Korean article uses.
- body_html: the translated body.

Korean article follows.
"""


def say(*lines):
    with _print_lock:
        for line in lines:
            print(line)
        sys.stdout.flush()


def load_config():
    path = os.path.join(HERE, "config.json")
    if not os.path.exists(path):
        sys.exit("config.json이 없습니다. config.example.json을 복사해 키를 채우세요.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_korean(path):
    """발행된 기사에서 번역에 필요한 것만 뽑는다."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    meta = lambda name: (re.search(r'<meta name="%s" content="([^"]*)"' % name, raw)
                         or [None, ""])[1]
    title = re.search(r"<title>(.*?)</title>", raw, re.S)
    title = html.unescape(title.group(1)) if title else ""
    if title.endswith(article.TITLE_SUFFIX):
        title = title[: -len(article.TITLE_SUFFIX)]
    marker = "것입니다.</p>"
    start, end = raw.find(marker), raw.find('<div class="disclaimer"')
    if start == -1 or end == -1:
        raise ValueError("본문 구간을 찾지 못했습니다")
    return {
        "title": title.strip(),
        "description": html.unescape(meta("description")),
        "category": html.unescape(meta("fs:category")),
        "eyebrow": html.unescape(meta("fs:eyebrow")),
        "read": html.unescape(meta("fs:read")),
        "video": html.unescape(meta("fs:video")),
        "date": html.unescape(meta("fs:date")),
        "body": raw[start + len(marker):end].strip(),
        "source_title": _source_title(raw),
    }


def _source_title(raw):
    m = re.search(r'class="source-note">원본 영상: <a[^>]*>(.*?)</a>', raw, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""


def structure_note(ko_body):
    """원문 구조를 숫자로 못박아 프롬프트에 넣는다.

    "새 blockquote를 만들지 마라"는 추상적 금지만으로는 새는 경우가 있었다. 세계
    기사(blockquote 0개)를 번역하니 13개, 프롬프트를 강화해 다시 시도해도 8개가 생겼다.
    개수를 명시하면 지킬 가능성이 높아진다. check_structure가 최종 방어선이다.
    """
    h2 = len(re.findall(r"<h2[ >]", ko_body))
    bq = len(re.findall(r"<blockquote[ >]", ko_body))
    note = (f"\nThe Korean body contains exactly {h2} <h2> elements and exactly {bq} "
            f"<blockquote> elements. Your body_html MUST contain exactly {h2} <h2> and "
            f"exactly {bq} <blockquote>.")
    if bq == 0:
        note += (" There are NO blockquotes in this article. Do not add any. Every quoted"
                 " phrase stays inline inside its <p>, translated into English.")
    return note


def translate(cfg, ko):
    """한국어 기사 필드 -> 영어 필드. Gemini 호출 1회."""
    payload = {
        "contents": [{"parts": [{"text": PROMPT + structure_note(ko["body"]) + "\n\n" + json.dumps({
            "title": ko["title"], "description": ko["description"],
            "eyebrow": ko["eyebrow"], "body_html": ko["body"],
        }, ensure_ascii=False)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "maxOutputTokens": cfg.get("max_output_tokens", 32768),
        },
    }
    # 키 순환·재시도·잘림 검사를 gemini.request가 한다. 초안 생성과 같은 경로다.
    return gemini.request(cfg, payload, timeout=300)


def check_structure(ko_body, en_body):
    """번역이 원문 구조를 바꾸지 않았는지. 어긋나면 예외.

    실측에서 한국어판에 blockquote가 0개인 기사를 번역했더니 영어판에 13개가 생겼다.
    본문 안 인용부호("전국 총파업이다!")를 blockquote로 승격시킨 것이다. 프롬프트로
    금지해도 새는 경우가 있으므로 개수로 막는다.
    """
    for tag in ("h2", "blockquote"):
        a = len(re.findall(r"<%s[ >]" % tag, ko_body))
        b = len(re.findall(r"<%s[ >]" % tag, en_body))
        if a != b:
            raise ValueError(f"<{tag}> 개수가 다릅니다 (원문 {a} vs 번역 {b}) — "
                             "번역이 구조를 바꿨습니다")
    return en_body


def render_en(ko, en):
    """영어판 HTML. 한국어판과 같은 골격에 lang과 언어 전환 링크만 다르다."""
    body = article.tidy_body(article.validate_body(en["body_html"]))
    esc = lambda v: html.escape(str(v), quote=True)
    vid = ko["video"]
    disclaimer = (
        "This article summarises the content of a YouTube video and reflects the "
        "personal views of the people appearing in it. Factory Magazine has not "
        "verified or endorsed these statements.")
    if ko["category"] in ("암호화폐", "경제"):
        disclaimer += (" It is not investment advice. Investments carry the risk of "
                       "loss, and any decision is the reader's own responsibility.")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{esc(en['title'])}{article.TITLE_SUFFIX}</title>
<meta name="description" content="{esc(en['description'])}" />
<link rel="alternate" hreflang="ko" href="{esc(ko['slug'])}.html" />
<meta name="fs:category" content="{esc(ko['category'])}" />
<meta name="fs:eyebrow" content="{esc(en['eyebrow'])}" />
<meta name="fs:read" content="{esc(ko['read'])}" />
<meta name="fs:video" content="{esc(vid)}" />
<meta name="fs:lang" content="en" />
<link rel="stylesheet" href="../css/style.css" />
</head>
<body>

{article._NAV}

<header class="article-hero">
  <div class="wrap">
    <a href="index.html" class="back-link">← All articles</a><a href="{esc(ko['slug'])}.html" class="lang-switch">한국어</a>
    <span class="section-eyebrow">{esc(en['eyebrow'])}</span>
    <h1>{esc(en['title'])}</h1>
    <div class="article-meta"><span class="byline-avatar">FS</span><span class="byline-name">{article.BYLINE}</span> · <span>{esc(ko['read'])} min read</span></div>
  </div>
</header>

<article class="article-content">

  <div class="video-embed">
    <iframe src="https://www.youtube.com/embed/{vid}" title="{esc(ko['source_title'])}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen loading="lazy"></iframe>
  </div>
  <p class="source-note">Source: <a href="https://www.youtube.com/watch?v={vid}" target="_blank" rel="noopener">{esc(ko['source_title'])}</a>. Summarised from that video.</p>

{body}

  <div class="disclaimer">
    {html.escape(disclaimer)}
  </div>

</article>

{article._FOOTER}

<script src="../js/main.js"></script>
</body>
</html>
"""


def add_switch_to_korean(path, slug):
    """한국어판에 English 링크를 붙인다. 이미 있으면 아무것도 하지 않는다."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if 'class="lang-switch"' in raw:
        return False
    old = '<a href="index.html" class="back-link">← 아티클 목록으로</a>'
    new = old + f'<a href="{slug}-en.html" class="lang-switch">English</a>'
    if old not in raw:
        return False
    raw = raw.replace(old, new, 1)
    if '<link rel="alternate"' not in raw:
        raw = raw.replace('<link rel="stylesheet"',
                          f'<link rel="alternate" hreflang="en" href="{slug}-en.html" />\n'
                          '<link rel="stylesheet"', 1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(raw)
    return True


def one(cfg, slug):
    src = os.path.join(ARTICLES, slug + ".html")
    dst = os.path.join(ARTICLES, slug + "-en.html")
    try:
        ko = read_korean(src)
        ko["slug"] = slug
        en, usage = translate(cfg, ko)
        check_structure(ko["body"], en["body_html"])
        with open(dst, "w", encoding="utf-8", newline="") as f:
            f.write(render_en(ko, en))
        add_switch_to_korean(src, slug)
        say(f"  완료 {slug}-en.html  (토큰 {usage.get('promptTokenCount')})",
            f"        {en['title'][:74]}")
        return {"slug": slug, "usage": usage}
    except Exception as e:
        say(f"  실패 {slug}: {e}")
        return {"slug": slug, "error": e}


def targets(args, force):
    rows = []
    for path in sorted(glob.glob(os.path.join(ARTICLES, "*.html"))):
        slug = os.path.splitext(os.path.basename(path))[0]
        if slug == "index" or slug.endswith("-en"):
            continue
        if args and not any(a in slug for a in args):
            continue
        if not force and os.path.exists(os.path.join(ARTICLES, slug + "-en.html")):
            continue
        rows.append(slug)
    return rows


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    force = "--force" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    cfg = load_config()

    slugs = targets(args, force)
    if not slugs:
        print("번역할 기사가 없습니다. 이미 영어판이 있으면 --force로 다시 만듭니다.")
        return 0

    print(f"{len(slugs)}편 번역 (최대 {MAX_PARALLEL}개 동시):")
    for s in slugs:
        print(f"  - {s}")
    print()
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        results = list(pool.map(lambda s: one(cfg, s), slugs))

    ok = [r for r in results if "error" not in r]
    total = sum(r["usage"].get("promptTokenCount", 0) for r in ok)
    print(f"\n성공 {len(ok)}건 / 실패 {len(results) - len(ok)}건  ·  총 토큰 {total:,}")
    if ok:
        print("한국어판에는 English 링크가 붙었습니다. 브라우저로 확인한 뒤 git push 하세요.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
