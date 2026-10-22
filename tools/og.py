# -*- coding: utf-8 -*-
"""공유 미리보기(카톡·페이스북·X) 태그와 탭 아이콘 (2026-10-21).

모든 페이지 <head>에 <!-- OG:START --> ... <!-- OG:END --> 묶음을 넣거나 갱신한다.
  - 기사: 제목·요약·카드 사진(fs:photo, 없으면 대표 이미지)
  - 그 밖의 페이지: 페이지 제목·설명 + 대표 이미지(images/og.png)
publish.py가 발행·인덱스 재생성 때마다 부른다. 처음 한 번은 전체에 돌린다:

    py -3 og.py          articles/*.html 전체 갱신

도메인을 사면 ORIGIN 한 곳만 바꾸고 다시 돌리면 된다 (publish.SITE_BASE 와 함께).
"""
import glob
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ARTICLES = os.path.join(HERE, "..", "articles")
ORIGIN = "https://factorysignal-magazine.vercel.app"
DEFAULT_IMAGE = ORIGIN + "/images/og.png"
START, END = "<!-- OG:START -->", "<!-- OG:END -->"
SITE_NAME = "Factory Magazine"


def _meta(text, name):
    m = re.search(rf'<meta name="{re.escape(name)}" content="([^"]*)"', text)
    return html.unescape(m.group(1)) if m else ""


def block(title, desc, url, image, kind="website"):
    e = lambda v: html.escape(v, quote=True)
    return "\n".join([
        START,
        f'<meta property="og:site_name" content="{SITE_NAME}" />',
        f'<meta property="og:type" content="{kind}" />',
        f'<meta property="og:title" content="{e(title)}" />',
        f'<meta property="og:description" content="{e(desc)}" />',
        f'<meta property="og:url" content="{e(url)}" />',
        f'<meta property="og:image" content="{e(image)}" />',
        '<meta property="og:locale" content="ko_KR" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        '<link rel="icon" href="../favicon.svg" type="image/svg+xml" />',
        '<link rel="apple-touch-icon" href="../images/apple-touch-icon.png" />',
        END,
    ])


def apply(text, slug):
    """페이지 HTML에 공유 태그 묶음을 넣는다(있으면 바꾼다)."""
    t = re.search(r"<title>(.*?)</title>", text, re.S)
    title = html.unescape(t.group(1)).strip() if t else SITE_NAME
    title = re.sub(r"\s+—\s+Factory Magazine$", "", title) if slug != "index" else "Factory Magazine — 세계는 몇 %로 보고 있을까"
    desc = _meta(text, "description") or "지금 가장 뜨거운 질문 10개. 해외 예측시장 확률을 보고 예/아니오로 가상 예측해 보세요."
    photo = _meta(text, "fs:photo")
    is_article = bool(_meta(text, "fs:date") or _meta(text, "fs:market"))
    url = f"{ORIGIN}/articles/{slug}.html" if slug != "index" else f"{ORIGIN}/articles/index.html"
    new = block(title, desc, url, photo or DEFAULT_IMAGE, "article" if is_article else "website")
    if START in text:
        return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: new, text, flags=re.S)
    return text.replace('<link rel="stylesheet"', new + '\n<link rel="stylesheet"', 1)


def apply_file(path):
    slug = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8") as f:
        old = f.read()
    if '<link rel="stylesheet"' not in old:
        return False
    new = apply(old, slug)
    if new != old:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
    return new != old


def main():
    changed = sum(apply_file(p) for p in glob.glob(os.path.join(ARTICLES, "*.html")))
    print(f"공유 태그 갱신 {changed}개")


if __name__ == "__main__":
    main()
