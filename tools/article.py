# -*- coding: utf-8 -*-
"""기사 HTML 조립과 검증.

네트워크·파일 IO가 없는 순수 함수만 둔다. 이 파이프라인에서 가장 깨지기 쉬운 부분
(LLM 출력 -> 마크업 조립)을 네트워크 없이 반복 검증하기 위한 분리다.
"""
import html
import re
from html.parser import HTMLParser

CATEGORIES = ("정치", "경제", "암호화폐", "스포츠", "세계", "스타트업")

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
    <a href="https://predictanalytics-news.vercel.app" class="nav-cta" target="_blank" rel="noopener">앱 열기</a>
  </div>
</nav>"""

_FOOTER = """<footer>
  <div class="wrap">
    <div class="footer-top">
      <div class="footer-brand">
        <a href="index.html" class="nav-logo">Factory<span> Magazine</span></a>
        <p class="footer-tagline">노이즈 속에서, 신호를 찾습니다.</p>
        <p>정치·경제·암호화폐·스포츠·세계·스타트업 소식 뒤에 숨은 결정을 기록하는 콘텐츠 브랜드입니다.</p>
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
            <li><a href="https://predictanalytics-news.vercel.app" target="_blank" rel="noopener">Factory Signal</a></li>
            <li><a href="https://predictanalytics-news.vercel.app/terms.html" target="_blank" rel="noopener">이용약관</a></li>
            <li><a href="https://predictanalytics-news.vercel.app/privacy.html" target="_blank" rel="noopener">개인정보처리방침</a></li>
          </ul>
        </div>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 Factory Magazine</span>
      <span>$SIGNAL은 현금화·환전이 불가능한 서비스 내 유틸리티 토큰입니다.</span>
    </div>
  </div>
</footer>"""


CARDS_START = "<!-- CARDS:START -->"
CARDS_END = "<!-- CARDS:END -->"


def card_html(meta):
    """인덱스 카드 하나. meta: slug, category, eyebrow, title, description, read, video

    카테고리 색은 CSS가 data-category로 붙이므로 여기서 색을 정하지 않는다
    (css/style.css의 .article-card[data-category="…"] 규칙).
    """
    esc = lambda v: html.escape(str(v), quote=True)
    validate_category(meta["category"])
    return (
        f'          <a href="{esc(meta["slug"])}.html" class="article-card" '
        f'data-category="{esc(meta["category"])}">\n'
        f'            <div class="article-thumb article-thumb--video" '
        f'style="background-image:url(\'https://img.youtube.com/vi/'
        f'{esc(meta["video"])}/hqdefault.jpg\');"><span>▶</span></div>\n'
        f'            <div class="article-body">\n'
        f'              <div class="article-tag">{esc(meta["eyebrow"])}</div>\n'
        f'              <h3>{esc(meta["title"])}</h3>\n'
        f'              <p>{esc(meta["description"])}</p>\n'
        f'              <div class="article-meta"><span class="byline-avatar">FS</span>'
        f'<span class="byline-name">{BYLINE}</span><span>·</span>'
        f'<span>{esc(meta["read"])}분 읽기</span></div>\n'
        f'            </div>\n'
        f'          </a>'
    )


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
    body = tidy_body(validate_body(fields["body_html"]))
    esc = lambda v: html.escape(str(v), quote=True)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{esc(fields['title'])}{TITLE_SUFFIX}</title>
<meta name="description" content="{esc(fields['description'])}" />
<meta name="fs:category" content="{esc(category)}" />
<meta name="fs:eyebrow" content="{esc(fields['eyebrow'])}" />
<meta name="fs:read" content="{esc(fields['read_minutes'])}" />
<meta name="fs:video" content="{esc(vid)}" />
<link rel="stylesheet" href="../css/style.css" />
</head>
<body>

{_NAV}

<header class="article-hero">
  <div class="wrap">
    <a href="index.html" class="back-link">← 아티클 목록으로</a>
    <span class="section-eyebrow">{esc(fields['eyebrow'])}</span>
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
