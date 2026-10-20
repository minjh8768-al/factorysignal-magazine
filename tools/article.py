# -*- coding: utf-8 -*-
"""기사 HTML 조립과 검증.

네트워크·파일 IO가 없는 순수 함수만 둔다. 이 파이프라인에서 가장 깨지기 쉬운 부분
(LLM 출력 -> 마크업 조립)을 네트워크 없이 반복 검증하기 위한 분리다.
"""
import html
import re
from html.parser import HTMLParser

CATEGORIES = ("정치", "경제", "암호화폐", "스포츠", "세계", "스타트업")

# 카드·기사 상단 꼬리표(eyebrow). 예전엔 LLM이 영문 라벨을 마음대로 지어 97종까지
# 늘어나 분류가 지저분해 보였다. 카테고리마다 이 목록 안에서만 고르게 한다.
# 각 목록의 첫 항목이 기본값이다.
EYEBROWS = {
    "경제": ("시장", "금리·정책", "산업·기업", "데이터분석"),
    "암호화폐": ("시장", "규제·정책", "산업"),
    "정치": ("국내정치", "정책", "안보·국방", "법·사법"),
    "세계": ("국제정세", "미국", "세계경제"),
    "스포츠": ("종합", "야구", "축구", "농구·배구"),
    "스타트업": ("창업·투자", "AI·테크", "전략"),
}

# 영어판 페이지에 쓰는 같은 꼬리표의 고정 번역.
EYEBROW_EN = {
    "시장": "Markets", "금리·정책": "Rates & Policy", "산업·기업": "Industry",
    "데이터분석": "Data Analysis", "규제·정책": "Regulation", "산업": "Industry",
    "국내정치": "Politics", "정책": "Policy", "안보·국방": "Defense", "법·사법": "Law & Courts",
    "국제정세": "World Affairs", "미국": "United States", "세계경제": "Global Economy",
    "종합": "Sports", "야구": "Baseball", "축구": "Football", "농구·배구": "Basketball & Volleyball",
    "창업·투자": "Startups", "AI·테크": "AI & Tech", "전략": "Strategy",
}

# 예전 영문 라벨·LLM 출력을 위 목록으로 옮기는 규칙. (카테고리, 패턴, 꼬리표) — 위에서부터 첫 일치.
_EYEBROW_RULES = (
    ("경제", r"data|데이터", "데이터분석"),
    ("경제", r"fed|monetary|policy|tax|rate|금리|정책|세제", "금리·정책"),
    ("경제", r"ai\b|tech|industry|semiconductor|pop|creator|business|산업|기업", "산업·기업"),
    ("암호화폐", r"policy|regulat|tax|규제|정책|세", "규제·정책"),
    ("암호화폐", r"industry|산업", "산업"),
    ("정치", r"defen[cs]e|security|안보|국방", "안보·국방"),
    ("정치", r"legal|trial|court|법|사법|재판", "법·사법"),
    ("정치", r"policy|정책", "정책"),
    ("세계", r"\bus\b|midterm|미국", "미국"),
    ("세계", r"economy|경제", "세계경제"),
    ("스포츠", r"kbo|baseball|야구", "야구"),
    ("스포츠", r"football|soccer|national team|mls|tactic|축구", "축구"),
    ("스포츠", r"basketball|volleyball|농구|배구", "농구·배구"),
    ("스타트업", r"ai\b|tech|silicon|테크", "AI·테크"),
    ("스타트업", r"strateg|전략", "전략"),
)


def poll_meta(question):
    """독자 투표 질문 메타 태그 한 줄. 질문이 없거나 형식이 어긋나면 빈 문자열 —
    투표가 빠질 뿐 기사 발행은 막지 않는다 (js/main.js가 메타가 있을 때만 투표를 띄운다)."""
    q = " ".join(str(question or "").split())
    if not (8 <= len(q) <= 80) or not q.endswith("?"):
        return ""
    return f'<meta name="fs:poll" content="{html.escape(q, quote=True)}" />\n'


def normalize_eyebrow(category, eyebrow, kind=None):
    """어떤 라벨이 와도 그 카테고리의 고정 꼬리표 중 하나로 바꾼다."""
    allowed = EYEBROWS.get(category)
    if not allowed:
        return eyebrow
    if kind == "analysis" and "데이터분석" in allowed:
        return "데이터분석"
    label = html.unescape(eyebrow or "").strip()
    if label in allowed:
        return label
    for cat, pattern, target in _EYEBROW_RULES:
        if cat == category and re.search(pattern, label, re.I):
            return target
    return allowed[0]

# 브랜드명은 여기 한 곳에만 둔다. 2026-08-03 리브랜딩(factorysignal -> Factory Magazine)
# 때, render()가 붙이는 제목 접미사와 publish.py가 떼는 접미사가 각각 하드코딩돼 있어서
# 카드 제목에 " — Factory Magazine"이 그대로 남는 버그가 났다.
# 붙이는 쪽과 떼는 쪽이 반드시 같은 값을 쓰게 한다.
BRAND = "Factory Magazine"
TITLE_SUFFIX = f" — {BRAND}"
BYLINE = f"{BRAND} 팀"

# body_html에 허용하는 태그. 이 밖의 태그가 오면 제거하지 않고 거부한다.
ALLOWED_TAGS = frozenset(
    ("p", "h2", "h3", "blockquote", "ul", "ol", "li", "strong", "em", "a", "br")
)

# 투자 위험 고지가 필요한 카테고리
_MONEY_CATS = frozenset(("암호화폐", "경제"))

_VIDEO_ID = r"([A-Za-z0-9_-]{11})"
_URL_PATTERNS = tuple(
    re.compile(p + _VIDEO_ID)
    for p in (
        r"youtu\.be/",
        r"youtube\.com/watch\?(?:[^#]*&)?v=",
        r"youtube\.com/embed/",
        r"youtube\.com/shorts/",
        r"youtube\.com/live/",
    )
)


def video_id(url):
    """유튜브 URL에서 11자 video id를 뽑는다."""
    for pattern in _URL_PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1)
    raise ValueError(f"유튜브 video id를 찾을 수 없습니다: {url}")


# 닫는 태그가 없는 것이 정상인 태그
_VOID_TAGS = frozenset(("br",))


class _TagCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.bad_tags = []
        self.bad_hrefs = []
        self.open_stack = []
        self.mismatched = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.bad_tags.append(tag)
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if not href.startswith(("http://", "https://", "#", "/")):
                self.bad_hrefs.append(href)
        if tag not in _VOID_TAGS:
            self.open_stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        # <br /> 형태. 여는 태그 검사만 하고 스택에는 쌓지 않는다.
        if tag not in ALLOWED_TAGS:
            self.bad_tags.append(tag)

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        if self.open_stack and self.open_stack[-1] == tag:
            self.open_stack.pop()
        else:
            self.mismatched.append(tag)


def validate_body(body_html):
    """허용 태그만 쓰였는지 검사한다. 위반이면 ValueError."""
    collector = _TagCollector()
    collector.feed(body_html)
    collector.close()
    if collector.bad_tags:
        raise ValueError(
            "본문에 허용되지 않은 태그가 있습니다: "
            + ", ".join(sorted(set(collector.bad_tags)))
        )
    if collector.bad_hrefs:
        raise ValueError(
            "본문에 허용되지 않은 링크가 있습니다: " + ", ".join(collector.bad_hrefs)
        )
    # 짝이 안 맞으면 본문이 잘렸다는 신호다. 잘린 기사가 발행되는 것을 막는다.
    if collector.open_stack:
        raise ValueError(
            "닫히지 않은 태그가 있습니다(본문이 잘렸을 수 있음): "
            + ", ".join(f"<{t}>" for t in collector.open_stack)
        )
    if collector.mismatched:
        raise ValueError(
            "짝이 맞지 않는 닫는 태그가 있습니다: "
            + ", ".join(f"</{t}>" for t in collector.mismatched)
        )
    return body_html


def validate_category(category):
    if category not in CATEGORIES:
        raise ValueError(
            f"카테고리가 6개 중 하나가 아닙니다: {category!r} "
            f"(허용: {', '.join(CATEGORIES)})"
        )
    return category


def clean_slug(raw):
    """파일명에 쓸 영문 슬러그로 정리한다."""
    slug = re.sub(r"[^a-z0-9]+", "-", (raw or "").lower()).strip("-")[:60].strip("-")
    if not slug:
        raise ValueError(f"쓸 수 있는 slug를 만들 수 없습니다: {raw!r}")
    return slug


_BLOCK_TAGS = ("p", "h2", "h3", "blockquote", "ul", "ol", "li")


def tidy_body(body_html):
    """블록 태그마다 줄을 나눈다.

    Gemini는 본문을 한 줄로 반환한다. 검수자가 브라우저로 보고 HTML을 직접 고치는
    워크플로라 사람이 읽을 수 있는 줄바꿈이 필요하다.
    """
    out = body_html
    for tag in _BLOCK_TAGS:
        out = out.replace(f"<{tag}>", f"\n<{tag}>").replace(f"</{tag}>", f"</{tag}>\n")
    lines = (line.strip() for line in out.split("\n"))
    return "\n".join("  " + line for line in lines if line)


def disclaimer_for(category):
    text = (
        "이 글은 유튜브 영상의 내용을 요약·정리한 것이며, 영상 출연자 개인의 견해입니다. "
        "Factory Magazine이 검증하거나 보증하는 내용이 아닙니다."
    )
    if category in _MONEY_CATS:
        text += (
            " 투자 조언이나 권유가 아니며, 투자에는 원금 손실 위험이 있으니 "
            "투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다."
        )
    return text


_NAV = """<nav class="nav">
  <button class="nav-toggle" aria-label="메뉴 열기">
    <span></span><span></span><span></span>
  </button>
  <a href="index.html" class="nav-logo">Factory<span> Magazine</span></a>
  <button type="button" class="nav-search" aria-label="검색" title="검색 (준비 중)">
    <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
  </button>
  <div class="nav-links">
    <a href="https://factorysignal-holdings.vercel.app" class="nav-holdings" target="_blank" rel="noopener">Factory<span> Holdings</span></a>
    <a href="https://t.me/+dQQkMVnpAqZhMDU9" class="nav-tg" target="_blank" rel="noopener"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.248l-2.012 9.483c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L7.48 14.697l-2.95-.924c-.642-.204-.654-.642.136-.953l11.5-4.432c.537-.194 1.006.131.396.86z"/></svg>텔레그램</a>
    <a href="subscribe.html" class="nav-cta">뉴스레터 받기</a>
  </div>
</nav>"""

_FOOTER = """<footer>
  <div class="wrap">
    <div class="footer-top">
      <div class="footer-brand">
        <a href="index.html" class="nav-logo">Factory<span> Magazine</span></a>
        <p class="footer-tagline">노이즈 속에서, 신호를 찾습니다.</p>
        <p>세계가 몇 %로 보는지, 확률로 읽는 뉴스를 만드는 매체입니다.</p>
      </div>
      <div class="footer-cols">
        <div class="footer-col">
          <h4>아티클</h4>
          <ul>
            <li><a href="index.html">전체 아티클</a></li>
            <li><a href="bitcoin-the-perfect-ledger.html">마켓 워치</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h4>링크</h4>
          <ul>
            <li><a href="subscribe.html">뉴스레터</a></li>
            <li><a href="privacy.html">개인정보처리방침</a></li>
          </ul>
        </div>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 Factory Magazine</span>
    </div>
  </div>
</footer>"""


CARDS_START = "<!-- CARDS:START -->"
CARDS_END = "<!-- CARDS:END -->"


# 썸네일에 크게 올릴 '핵심 숫자'. 단위가 붙은 숫자만, 의미가 큰 단위부터 찾는다
# (예: "미 10년물 국채금리 5%대" → '10년물'이 아니라 '5%').
_FIGURE_RES = [re.compile(r"\d[\d,.]*\s?" + u) for u in (
    r"(?:%p|%|bps|bp)",
    r"(?:조\s?원|억\s?원|만\s?원|천\s?원|원|만\s?달러|억\s?달러|달러)",
    r"(?:만\s?명|명|배)",
    r"(?:거래일|연전|연승|연패|차전|년물|개월|위|승|패|골|일|년)",
)]
# 숫자가 없으면 제목 속 짧은 인용어 (예: '노벨평화상', '연결')
_QUOTE_RE = re.compile(r"['‘\"“]([^'’\"”]{2,8})['’\"”]")


def key_figure(title):
    text = html.unescape(title or "")
    for rx in _FIGURE_RES:
        m = rx.search(text)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).strip()
    m = _QUOTE_RE.search(text)
    return m.group(1).strip() if m else ""


def thumb_html(meta):
    """카드 썸네일.

    영상 기사는 유튜브 이미지를 배경으로 쓴다. 분석 기사는 영상이 없어 그 URL 이
    깨진 이미지가 되므로, 사진을 <img> 로 깔고 그 위에 지표 차트를 얹는다.

    사진을 background-image 로 넣지 않는 이유: .article-thumb--data 가 카테고리
    그라디언트를 이기려고 background 에 !important 를 쓰는데, !important 는 인라인
    스타일까지 이겨서 사진이 통째로 사라졌다. <img> 는 그 싸움 밖에 있다.
    """
    esc = lambda v: html.escape(str(v), quote=True)
    nl = chr(10)
    if meta.get("video") and meta.get("photo"):
        # 뉴스처럼 보이게 실제 사진 + 분야 라벨. 남의 방송 화면은 쓰지 않는다.
        # 사진은 위키미디어 커먼즈(인물·팀 실사진, CC BY 등) 또는 Pexels(장면). CC BY 계열은
        # 출처 표기가 이용 조건이라 촬영자·라이선스를 사진 위에 작게 단다.
        credit, fallback = "", ""
        if meta.get("photo_license") == "원본 영상":
            # 원본 유튜브 영상 썸네일: 채널을 출처로 밝힌다. 고화질(maxres)이 없는 영상은 중간 화질로.
            credit = f'<span class="thumb-credit">출처: {esc(meta.get("photo_by") or "")} 유튜브</span>'
            low = meta["photo"].replace("maxresdefault", "mqdefault")
            fallback = f' onerror="this.onerror=null;this.src=\'{esc(low)}\'"'
        elif meta.get("photo_license"):
            credit = (f'<span class="thumb-credit">사진: {esc(meta.get("photo_by") or "")} · '
                      f'{esc(meta["photo_license"])}</span>')
        return (f'            <div class="article-thumb article-thumb--news">'
                f'<img class="thumb-photo" src="{esc(meta["photo"])}" alt="" loading="lazy"{fallback} />'
                f'<span class="thumb-cat">{esc(meta["category"])}</span>'
                f'{credit}</div>{nl}')
    if meta.get("video"):
        # 사진을 못 찾은 경우의 대체 썸네일: 분야 색 + 핵심어.
        # 2026-10-20: 남의 방송 썸네일(채널 로고·자막이 그대로 보임) 대신 우리 썸네일.
        # 분야 색 배경 + 제목에서 뽑은 핵심 숫자(없으면 꼬리표)를 크게. 영상은 기사 안에 그대로 있다.
        figure = meta.get("thumb") or key_figure(meta.get("title", ""))
        big = (f'<strong class="thumb-figure">{esc(figure)}</strong>' if figure
               else f'<strong class="thumb-figure thumb-figure--word">{esc(meta.get("eyebrow") or meta["category"])}</strong>')
        return (f'            <div class="article-thumb article-thumb--brand">'
                f'<span class="thumb-cat">{esc(meta["category"])}</span>{big}'
                f'<span class="thumb-mark">Factory Magazine</span>'
                f'</div>{nl}')
    photo = meta.get("photo") or ""
    klass = "article-thumb article-thumb--data"
    img = ""
    if photo:
        klass += " article-thumb--photo"
        img = (f'<img class="thumb-photo" src="{esc(photo)}" alt="" '
               f'loading="lazy" />')
    return (f'            <div class="{klass}">{img}{meta.get("thumb_svg") or ""}'
            f'<span class="thumb-badge">데이터</span></div>{nl}')

def card_html(meta):
    """인덱스 카드 하나. meta: slug, category, eyebrow, title, description, read, video

    카테고리 색은 CSS가 data-category로 붙이므로 여기서 색을 정하지 않는다
    (css/style.css의 .article-card[data-category="…"] 규칙).
    """
    esc = lambda v: html.escape(str(v), quote=True)
    validate_category(meta["category"])
    # 날짜가 없으면 뉴스가 언제 것인지 독자가 알 수 없다. fs:date(YYYY-MM-DD)를 점 표기로.
    date = meta.get("date") or ""
    date_html = (f'<span>·</span><time datetime="{esc(date)}">{esc(date.replace("-", "."))}</time>'
                 if date else "")
    return (
        f'          <a href="{esc(meta["slug"])}.html" class="article-card" '
        f'data-category="{esc(meta["category"])}">\n'
        + thumb_html(meta) +
        f'            <div class="article-body">\n'
        f'              <div class="article-tag">{esc(meta["eyebrow"])}</div>\n'
        f'              <h3>{esc(meta["title"])}</h3>\n'
        f'              <p>{esc(meta["description"])}</p>\n'
        f'              <div class="article-meta"><span class="byline-avatar">FS</span>'
        f'<span class="byline-name">{BYLINE}</span><span>·</span>'
        f'<span>{esc(meta["read"])}분 읽기</span>{date_html}</div>\n'
        f'            </div>\n'
        f'          </a>'
    )


TODAY_START = "<!-- TODAY:START -->"
TODAY_END = "<!-- TODAY:END -->"
_TODAY_FIRST = ("경제", "암호화폐")


def pick_today(rows, n=3):
    """첫 화면 '오늘의 핵심 3'. rows는 최신순. 가장 최근 발행일의 기사 중 경제·암호화폐를
    먼저, 그날 기사가 모자라면 그 전날 것으로 채운다."""
    if not rows:
        return []
    latest = rows[0]["date"]
    same_day = [r for r in rows if r["date"] == latest]
    same_day.sort(key=lambda r: 0 if r["category"] in _TODAY_FIRST else 1)
    picked = same_day[:n]
    for r in rows:
        if len(picked) >= n:
            break
        if r not in picked:
            picked.append(r)
    return picked


def today_html(items):
    """'오늘의 핵심 3' 목록 마크업. item: slug, category, title, line(한 줄 요약)."""
    esc = lambda v: html.escape(str(v), quote=True)
    lis = []
    for i, it in enumerate(items, 1):
        lis.append(
            f'          <li class="today-item" data-category="{esc(it["category"])}">'
            f'<span class="today-num">{i}</span>'
            f'<a href="{esc(it["slug"])}.html"><strong>{esc(it["title"])}</strong>'
            f'<span>{esc(it["line"])}</span></a></li>'
        )
    return "\n        <ol class=\"today-list\">\n" + "\n".join(lis) + "\n        </ol>\n        "


def replace_between(text, start_marker, end_marker, inner):
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"{start_marker} / {end_marker} 마커가 없습니다.")
    return text[:start + len(start_marker)] + inner + text[end:]


def replace_cards(index_html, cards):
    """마커 사이를 새 카드 목록으로 통째로 교체한다. 마커 밖은 건드리지 않는다."""
    start = index_html.find(CARDS_START)
    end = index_html.find(CARDS_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError(
            f"인덱스에 {CARDS_START} / {CARDS_END} 마커가 없습니다. "
            "articles/index.html의 .article-grid 안에 넣어주세요."
        )
    inner = ("\n" + "\n\n".join(cards) + "\n          ") if cards else ""
    return (index_html[:start + len(CARDS_START)] + inner + index_html[end:])


def render(fields, url):
    """검증된 필드로 완성 기사 HTML을 만든다.

    fields: title, description, slug, category, eyebrow, read_minutes,
            source_title, body_html
    """
    vid = video_id(url)
    category = validate_category(fields["category"])
    eyebrow = normalize_eyebrow(category, fields["eyebrow"])
    poll = poll_meta(fields.get("poll_question"))
    body = tidy_body(validate_body(fields["body_html"]))
    esc = lambda v: html.escape(str(v), quote=True)
    # 카드 썸네일 핵심어 (없거나 너무 짧으면 제목에서 숫자를 뽑는 쪽으로 물러선다)
    thumb = " ".join(str(fields.get("thumb_keyword") or "").split())[:12]
    thumb_tag = f'<meta name="fs:thumb" content="{esc(thumb)}" />\n' if len(thumb) >= 2 else ""
    # 카드 사진 (draft.py가 Pexels에서 찾아 넣는다). 없으면 글자 썸네일로 물러선다.
    photo = fields.get("photo") or {}
    if photo.get("url"):
        thumb_tag += f'<meta name="fs:photo" content="{esc(photo["url"])}" />\n'
        if photo.get("by"):
            thumb_tag += f'<meta name="fs:photo_by" content="{esc(photo["by"])}" />\n'
        for key in ("license", "src"):     # 커먼즈 사진의 출처 표기용
            if photo.get(key):
                thumb_tag += f'<meta name="fs:photo_{key}" content="{esc(photo[key])}" />\n'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{esc(fields['title'])}{TITLE_SUFFIX}</title>
<meta name="description" content="{esc(fields['description'])}" />
<meta name="fs:category" content="{esc(category)}" />
<meta name="fs:eyebrow" content="{esc(eyebrow)}" />
<meta name="fs:read" content="{esc(fields['read_minutes'])}" />
<meta name="fs:video" content="{esc(vid)}" />
{poll}{thumb_tag}<link rel="stylesheet" href="../css/style.css" />
</head>
<body>

{_NAV}

<header class="article-hero">
  <div class="wrap">
    <a href="index.html" class="back-link">← 아티클 목록으로</a>
    <span class="section-eyebrow">{esc(eyebrow)}</span>
    <h1>{esc(fields['title'])}</h1>
    <div class="article-meta"><span class="byline-avatar">FS</span><span class="byline-name">{BYLINE}</span> · <span>{esc(fields['read_minutes'])}분 읽기</span></div>
  </div>
</header>

<article class="article-content">

  <div class="video-embed">
    <iframe src="https://www.youtube.com/embed/{vid}" title="{esc(fields['source_title'])}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen loading="lazy"></iframe>
  </div>
  <p class="source-note">원본 영상: <a href="https://www.youtube.com/watch?v={vid}" target="_blank" rel="noopener">{esc(fields['source_title'])}</a>. 이하 내용은 해당 영상을 요약·정리한 것입니다.</p>

{body}

  <div class="disclaimer">
    {html.escape(disclaimer_for(category))}
  </div>

</article>

{_FOOTER}

<script src="../js/main.js"></script>
</body>
</html>
"""


# ── 첫 화면 구역 (2026-10-20, 뉴닉식 구성) ────────────────────────────
# 첫 화면은 기사 목록 하나가 끝없이 이어지면 허전해 보여서, 구역으로 나눈다:
#   대표 기사 1 + 최신 8 (HOME-TOP) / 분야별 3단·가로형 구역 (HOME-SECTIONS).
# 전체 목록과 분야 필터는 articles/all.html 로 옮겼다. 구역은 인덱스 재생성 때마다
# 최신 기사로 다시 채워진다. rows: publish.published() 결과 + 'line'(요약 한 줄).
HOME_TOP_START, HOME_TOP_END = "<!-- HOME-TOP:START -->", "<!-- HOME-TOP:END -->"
HOME_SEC_START, HOME_SEC_END = "<!-- HOME-SECTIONS:START -->", "<!-- HOME-SECTIONS:END -->"
HOME_COLUMNS = (("경제", ("경제",)), ("암호화폐", ("암호화폐",)), ("정치·세계", ("정치", "세계")))
HOME_ROWS = (("스포츠", ("스포츠",)), ("스타트업", ("스타트업",)))


def _short_date(d):
    return d[5:].replace("-", ".") if d else ""


def _home_card(r):
    esc = lambda v: html.escape(str(v), quote=True)
    return (f'<a class="home-card" href="{esc(r["slug"])}.html" data-category="{esc(r["category"])}">\n'
            + thumb_html(r) +
            f'<strong>{esc(r["title"])}</strong>'
            f'<span class="home-meta">{esc(r["category"])} · {_short_date(r["date"])}</span></a>')


def _home_text(r):
    esc = lambda v: html.escape(str(v), quote=True)
    return (f'<a class="home-text" href="{esc(r["slug"])}.html"><strong>{esc(r["title"])}</strong>'
            f'<span class="home-meta">{_short_date(r["date"])}</span></a>')


def _home_feature(r, cls="home-feature"):
    esc = lambda v: html.escape(str(v), quote=True)
    return (f'<div class="{cls}" data-category="{esc(r["category"])}">'
            f'<a class="home-feature-img" href="{esc(r["slug"])}.html">\n' + thumb_html(r) + '</a>'
            f'<div class="home-feature-body"><span class="home-cat">{esc(r["category"])}</span>'
            f'<a href="{esc(r["slug"])}.html"><h3>{esc(r["title"])}</h3></a>'
            f'<p>{esc(r.get("line") or r["description"])}</p>'
            f'<span class="home-meta">{_short_date(r["date"])}</span></div></div>')


def home_top_html(rows):
    """대표 기사 1 + 최신 8. 대표는 최근 발행일의 경제·암호화폐 기사 중 사진 있는 것 우선."""
    if not rows:
        return ""
    latest = rows[0]["date"]
    pool = [r for r in rows if r["date"] == latest]
    feature = next((r for r in pool if r["category"] in _TODAY_FIRST and r.get("photo")),
                   next((r for r in pool if r.get("photo")), rows[0]))
    rest = [r for r in rows if r is not feature][:8]
    return ("\n" + _home_feature(feature) +
            '\n<div class="home-grid">\n' + "\n".join(_home_card(r) for r in rest) + "\n</div>\n")


def home_sections_html(rows, skip=8):
    """분야별 구역. 맨 위(대표+최신 8)에 나온 기사는 되도록 빼고 고른다."""
    esc = lambda v: html.escape(str(v), quote=True)
    shown = {r["slug"] for r in rows[:skip + 1]}
    pick = lambda cats, n: ([r for r in rows if r["category"] in cats and r["slug"] not in shown]
                            or [r for r in rows if r["category"] in cats])[:n]
    out = ['\n<div class="home-columns">']
    for title, cats in HOME_COLUMNS:
        items = pick(cats, 4)
        if not items:
            continue
        out.append(f'<section class="home-col"><a class="home-head" href="all.html?cat={esc(cats[0])}">'
                   f'{esc(title)} <span>›</span></a>' + _home_card(items[0]) +
                   "".join(_home_text(r) for r in items[1:]) + "</section>")
    out.append("</div>")
    for title, cats in HOME_ROWS:
        items = pick(cats, 5)
        if not items:
            continue
        out.append(f'<section class="home-row"><a class="home-head" href="all.html?cat={esc(cats[0])}">'
                   f'{esc(title)} <span>›</span></a>' + _home_feature(items[0], "home-feature home-feature--row") +
                   '<div class="home-row-list">' + "".join(_home_feature(r, "home-mini") for r in items[1:]) +
                   "</div></section>")
    return "\n".join(out) + "\n"
