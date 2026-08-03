# -*- coding: utf-8 -*-
"""초안 발행 · 발행 취소.

    py -3 publish.py                    드라이런 — 무엇이 바뀔지만 출력
    py -3 publish.py --apply            _drafts/*.html 전부 발행
    py -3 publish.py --apply <slug>...  지정한 초안만 발행
    py -3 publish.py --list             현재 자동발행된 기사 목록
    py -3 publish.py --remove <slug>... 발행 취소 (드라이런)
    py -3 publish.py --remove --apply <slug>...   실제 삭제

인덱스는 articles/index.html의 <!-- CARDS:START/END --> 사이만 재생성한다.
손으로 쓴 기존 카드 4개는 마커 밖에 있어 절대 건드리지 않는다.
자동발행 기사는 fs:date 메타로 식별한다.
"""
import glob
import html
import os
import re
import sys

import article

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DRAFTS = os.path.join(ROOT, "_drafts")
ARTICLES = os.path.join(ROOT, "articles")
INDEX = os.path.join(ARTICLES, "index.html")

DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.html$")


def _meta(text, name):
    m = re.search(r'<meta name="%s" content="([^"]*)"' % re.escape(name), text)
    return html.unescape(m.group(1)) if m else None


def read_meta(path):
    """기사/초안 HTML에서 카드에 필요한 값을 뽑는다."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    title = re.search(r"<title>(.*?)</title>", text, re.S)
    title = html.unescape(title.group(1)) if title else ""
    if title.endswith(article.TITLE_SUFFIX):
        title = title[: -len(article.TITLE_SUFFIX)]
    return {
        "title": title.strip(),
        "description": _meta(text, "description") or "",
        "category": _meta(text, "fs:category"),
        "eyebrow": _meta(text, "fs:eyebrow"),
        "read": _meta(text, "fs:read"),
        "video": _meta(text, "fs:video"),
        "date": _meta(text, "fs:date"),
        "_text": text,
    }


def published():
    """fs:date가 있는 기사(=자동발행분)를 최신순으로 반환한다."""
    rows = []
    for path in glob.glob(os.path.join(ARTICLES, "*.html")):
        slug = os.path.splitext(os.path.basename(path))[0]
        if slug == "index":
            continue
        meta = read_meta(path)
        if meta["date"]:
            meta["slug"] = slug
            rows.append(meta)
    rows.sort(key=lambda m: (m["date"], m["slug"]), reverse=True)
    return rows


def rebuild_index(apply_changes):
    rows = published()
    cards = [article.card_html(m) for m in rows]
    with open(INDEX, encoding="utf-8") as f:
        old = f.read()
    new = article.replace_cards(old, cards)
    if apply_changes and new != old:
        with open(INDEX, "w", encoding="utf-8") as f:
            f.write(new)
    return rows, new != old


def stamp_date(text, date):
    """발행일을 fs:date로 심는다. 카드 정렬 근거이자 발행 기록이다."""
    if 'name="fs:date"' in text:
        return re.sub(r'<meta name="fs:date" content="[^"]*"',
                      f'<meta name="fs:date" content="{date}"', text)
    return text.replace('<meta name="fs:video"',
                        f'<meta name="fs:date" content="{date}" />\n<meta name="fs:video"', 1)


def do_publish(slugs, apply_changes):
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(DRAFTS, "*.html")))
    if slugs:
        files = [f for f in files if any(s in f for s in slugs)]
    if not files:
        print("발행할 초안이 없습니다.")
        return 0

    planned = []
    for name in files:
        m = DATE_PREFIX.match(name)
        if not m:
            print(f"  건너뜀 (파일명이 YYYY-MM-DD-slug.html 형식이 아님): {name}")
            continue
        date, slug = m.group(1), m.group(2)
        src = os.path.join(DRAFTS, name)
        dst = os.path.join(ARTICLES, slug + ".html")
        meta = read_meta(src)
        missing = [k for k in ("category", "eyebrow", "read", "video") if not meta[k]]
        if missing:
            print(f"  건너뜀 ({name}): fs: 메타 누락 {missing}")
            continue
        article.validate_category(meta["category"])
        planned.append((src, dst, slug, date, meta, os.path.exists(dst)))

    for src, dst, slug, date, meta, overwrite in planned:
        flag = " (기존 파일 덮어씀)" if overwrite else ""
        print(f"  [{meta['category']}] {slug}.html{flag}")
        print(f"      {meta['title']}")

    if not apply_changes:
        print(f"\n드라이런입니다. {len(planned)}건 발행 예정. 실제로 하려면 --apply")
        return 0

    for src, dst, slug, date, meta, _ in planned:
        with open(dst, "w", encoding="utf-8") as f:
            f.write(stamp_date(meta["_text"], date))
        os.remove(src)
    rows, changed = rebuild_index(True)
    print(f"\n발행 완료 {len(planned)}건. 인덱스 자동카드 {len(rows)}개.")
    print("git push 하면 사이트에 반영됩니다.")
    return 0


def do_remove(slugs, apply_changes):
    if not slugs:
        print("삭제할 slug을 지정하세요. 목록은 --list")
        return 1
    rows = {m["slug"]: m for m in published()}
    targets = []
    for s in slugs:
        hits = [slug for slug in rows if s in slug]
        if not hits:
            print(f"  없음: {s}")
            continue
        targets.extend(hits)
    if not targets:
        print("삭제 대상이 없습니다.")
        return 1

    for slug in targets:
        print(f"  삭제 [{rows[slug]['category']}] {slug}.html — {rows[slug]['title']}")
    if not apply_changes:
        print(f"\n드라이런입니다. {len(targets)}건 삭제 예정. 실제로 하려면 --apply 추가")
        return 0

    for slug in targets:
        os.remove(os.path.join(ARTICLES, slug + ".html"))
    left, _ = rebuild_index(True)
    print(f"\n삭제 완료 {len(targets)}건. 남은 자동카드 {len(left)}개.")
    print("git push 하면 사이트에서 사라집니다.")
    return 0


def do_list():
    rows = published()
    if not rows:
        print("자동발행된 기사가 없습니다.")
        return 0
    print(f"자동발행 기사 {len(rows)}건 (최신순):\n")
    for m in rows:
        print(f"  {m['date']}  [{m['category']:5}]  {m['slug']}")
        print(f"              {m['title']}")
    return 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv[1:]
    apply_changes = "--apply" in args
    remove = "--remove" in args
    listing = "--list" in args
    slugs = [a for a in args if not a.startswith("--")]

    if listing:
        return do_list()
    if remove:
        return do_remove(slugs, apply_changes)
    return do_publish(slugs, apply_changes)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
