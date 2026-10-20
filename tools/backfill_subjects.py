# -*- coding: utf-8 -*-
"""예전 기사 중 제목에 주인공(인물·팀·기관)이 있는 것의 카드 사진을 커먼즈 실사진으로 바꾼다.

    py -3 backfill_subjects.py            드라이런 — 주인공별 기사 수
    py -3 backfill_subjects.py --apply    실제로 fs:photo* 메타를 바꾸고 인덱스 재생성

키가 필요 없어 PC에서 바로 돌린다. 커먼즈에서 못 찾은 기사는 기존 Pexels 사진을 그대로 둔다.
2026-10-20 "리센느 사진, 국가대표 사진처럼 기사에 맞게" 요청으로 작성.
"""
import glob
import html
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import commons  # noqa: E402
import pexels   # noqa: E402
import publish  # noqa: E402

PHOTO_META = re.compile(r'<meta name="fs:photo(?:_by|_license|_src)?" content="[^"]*" />\r?\n')


def main(argv):
    apply_changes = "--apply" in argv
    targets = []
    for path in sorted(glob.glob(os.path.join(ROOT, "articles", "*.html"))):
        if path.endswith(("index.html", "all.html", "-en.html", "subscribe.html", "privacy.html")):
            continue
        text = io.open(path, encoding="utf-8").read()
        if 'name="fs:video"' not in text:
            continue
        title = html.unescape((re.search(r"<title>(.*?)</title>", text, re.S) or [None, ""])[1])
        eyebrow = html.unescape((re.search(r'fs:eyebrow" content="([^"]*)', text) or [None, ""])[1])
        subject = commons.subject_for(title, eyebrow, os.path.basename(path)[:-5])
        if subject:
            targets.append((path, subject, title))

    subjects = sorted({s for _, s, _ in targets})
    print(f"주인공이 있는 기사 {len(targets)}편, 주인공 {len(subjects)}개")
    for s in subjects:
        print(f"  {sum(1 for _, x, _ in targets if x == s):3d}  {s}")
    if not apply_changes:
        print("드라이런입니다. 실제로 하려면 --apply")
        return 0

    pools = {s: commons.candidates(s) for s in subjects}
    done, missing = 0, []
    for path, subject, title in targets:
        pool = pools.get(subject) or []
        if not pool:
            missing.append(subject)
            continue
        slug = os.path.basename(path)[:-5]
        p = pool[pexels.pick_index(slug, len(pool))]
        esc = lambda v: html.escape(v, quote=True)
        raw = io.open(path, encoding="utf-8", newline="").read()
        nl = "\r\n" if "\r\n" in raw else "\n"
        raw = PHOTO_META.sub("", raw)
        tag = "".join(f'<meta name="fs:photo{suffix}" content="{esc(p[k])}" />{nl}'
                      for suffix, k in (("", "url"), ("_by", "by"), ("_license", "license"), ("_src", "src"))
                      if p.get(k))
        new, n = re.subn(r'(<link rel="stylesheet")', lambda mm: tag + mm.group(1), raw, count=1)
        if n:
            io.open(path, "w", encoding="utf-8", newline="").write(new)
            done += 1
    rows, _ = publish.rebuild_index(True)
    print(f"실사진으로 바꾼 기사 {done}편. 못 찾은 주인공: {sorted(set(missing)) or '없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
