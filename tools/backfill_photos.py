# -*- coding: utf-8 -*-
"""사진이 없는 영상 요약 기사에 카드 사진(Pexels)을 한 번에 붙인다.

    py -3 backfill_photos.py            드라이런 — 검색어별 기사 수만 출력
    py -3 backfill_photos.py --apply    실제로 fs:photo 메타를 넣고 인덱스 재생성

Pexels 무료 한도는 시간당 200회라, 기사마다 부르지 않고 검색어마다 한 번(40장)만
불러 기사끼리 나눠 쓴다. 키는 config.json 의 pexels_api_key (GitHub Actions 에서는
PEXELS_API_KEY 비밀값 → config_from_env.py). 2026-10-20 글자 썸네일 → 사진 전환 때 작성.
"""
import glob
import html
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import pexels   # noqa: E402
import publish  # noqa: E402

PER_QUERY = 40


def search(key, query):
    url = pexels.ENDPOINT.format(n=PER_QUERY, q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return [{"url": p["src"]["landscape"], "by": p.get("photographer", "")}
                for p in json.loads(r.read().decode("utf-8")).get("photos", [])]


def main(argv):
    apply_changes = "--apply" in argv
    targets = []
    for path in sorted(glob.glob(os.path.join(ROOT, "articles", "*.html"))):
        if path.endswith(("index.html", "all.html", "-en.html", "subscribe.html", "privacy.html")):
            continue
        text = io.open(path, encoding="utf-8").read()
        m = lambda n: (re.search(r'<meta name="%s" content="([^"]*)"' % n, text) or [None, ""])[1]
        if not m("fs:video") or m("fs:photo"):
            continue
        title = html.unescape((re.search(r"<title>(.*?)</title>", text, re.S) or [None, ""])[1])
        q = pexels.query_for(title, html.unescape(m("fs:eyebrow")), m("fs:category"))
        targets.append((path, q))

    queries = sorted({q for _, q in targets})
    print(f"사진 없는 영상 기사 {len(targets)}편, 검색어 {len(queries)}개")
    for q in queries:
        print(f"  {sum(1 for _, x in targets if x == q):3d}  {q}")
    if not apply_changes:
        print("드라이런입니다. 실제로 하려면 --apply")
        return 0

    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        key = json.load(f).get("pexels_api_key", "")
    if not key:
        print("pexels_api_key 가 없습니다.")
        return 1
    pools = {}
    for q in queries:
        try:
            pools[q] = search(key, q)
        except Exception as e:
            print(f"  검색 실패 {q}: {e}")
            pools[q] = []

    used = {}
    done = 0
    for path, q in targets:
        pool = pools.get(q) or []
        if not pool:
            continue
        slug = os.path.basename(path)[:-5]
        # 같은 검색어 기사끼리 가능한 한 다른 사진을 쓴다.
        i = pexels.pick_index(slug, len(pool))
        seen = used.setdefault(q, set())
        for k in range(len(pool)):
            if (i + k) % len(pool) not in seen:
                i = (i + k) % len(pool)
                break
        seen.add(i)
        p = pool[i]
        esc = lambda v: html.escape(v, quote=True)
        tag = f'<meta name="fs:photo" content="{esc(p["url"])}" />\n'
        if p["by"]:
            tag += f'<meta name="fs:photo_by" content="{esc(p["by"])}" />\n'
        raw = io.open(path, encoding="utf-8", newline="").read()
        nl = "\r\n" if "\r\n" in raw else "\n"
        new, n = re.subn(r'(<link rel="stylesheet")', lambda mm: tag.replace("\n", nl) + mm.group(1), raw, count=1)
        if n:
            io.open(path, "w", encoding="utf-8", newline="").write(new)
            done += 1
    rows, _ = publish.rebuild_index(True)
    print(f"사진 추가 {done}편. 인덱스 카드 {len(rows)}개.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
