# -*- coding: utf-8 -*-
"""손으로(Claude Code 세션에서) 쓴 예측 기사를 승인 대기 초안으로 만든다 (2026-10-21).

API 요금 없이 팀 요금제 안에서 기사를 쓰는 경로: 사용자가 세션에서 "오늘 예측 기사 써 줘"라고 하면
Claude가 웹 검색으로 확인하며 기사를 JSON으로 쓰고, 이 스크립트가 자동 작성(market_article.py)과
똑같은 모양의 HTML로 만든다. 만든 파일은 upload-draft 워크플로로 올려 관리자 '승인 대기'에 넣는다.

    py -3 manual_draft.py 기사.json          _drafts/ 에 초안 + data/drafted.json 기록
    py -3 manual_draft.py 기사.json --upload  위 + GitHub upload-draft 워크플로 실행 (gh 필요)

기사.json: {"market": "질문 id", "kind": "preview"|"result", "title", "description", "category",
            "eyebrow", "slug", "body_html", "photo_subject"(선택, 커먼즈 검색어) 또는 "photo"({url,by,license,src})}
"""
import base64
import datetime
import json
import os
import subprocess
import sys

import article
import commons
import market_article as ma


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        a = json.load(f)
    with open(os.path.join(ma.DATA, "markets.json"), encoding="utf-8") as f:
        m = next(x for x in json.load(f)["markets"] if x["id"] == str(a["market"]))
    kind = a["kind"]
    assert kind in ("preview", "result")
    body = article.tidy_body(article.validate_body(a["body_html"]))
    read = max(2, round(len(__import__("re").sub(r"<[^>]+>", "", body)) / 500))
    photo = a.get("photo") or (commons.search(a["photo_subject"], avoid=commons.used_photos()) if a.get("photo_subject") else None)
    fields = {"title": a["title"], "description": a["description"], "category": a["category"],
              "eyebrow": a.get("eyebrow", "")}
    page = ma.render(fields, body, read, photo, m, kind)
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")
    slug = article.clean_slug(a["slug"])
    if os.path.exists(os.path.join(ma.ARTICLES, slug + ".html")):
        slug = f"{slug}-{m['id']}"
    name = f"{today}-{slug}.html"
    os.makedirs(ma.DRAFTS, exist_ok=True)
    with open(os.path.join(ma.DRAFTS, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    drafted = ma.load_drafted()
    drafted.setdefault(m["id"], {})[kind] = today
    with open(ma.DRAFTED, "w", encoding="utf-8", newline="\n") as f:
        json.dump(drafted, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"초안 {name} ({len(page)}자, 사진: {(photo or {}).get('url', '없음')[:70]})")
    if "--upload" in sys.argv:
        b64 = base64.b64encode(page.encode("utf-8")).decode()
        subprocess.run(["gh", "workflow", "run", "upload-draft.yml", "--ref", "master",
                        "-f", f"name={name}", "-f", f"html_b64={b64}"], check=True)
        print("  → upload-draft 실행 (1~2분 뒤 승인 대기)")


if __name__ == "__main__":
    main()
