# -*- coding: utf-8 -*-
"""유튜브 URL -> 검수용 기사 초안 HTML.

    py -3 draft.py https://www.youtube.com/watch?v=xxxxxxxxxxx

_drafts/YYYY-MM-DD-<slug>.html 을 만든다. articles/ 는 건드리지 않는다.
브라우저로 그 파일을 열어 검수한 뒤 발행한다.
"""
import datetime
import json
import os
import sys

import article
import gemini
import youtube

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DRAFTS = os.path.join(ROOT, "_drafts")
ARTICLES = os.path.join(ROOT, "articles")


def load_config():
    path = os.path.join(HERE, "config.json")
    if not os.path.exists(path):
        sys.exit("config.json이 없습니다. config.example.json을 복사해 키를 채우세요.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def unique_slug(slug, date):
    """articles/ 와 _drafts/ 를 모두 확인해 겹치지 않는 파일명을 만든다."""
    for n in range(1, 100):
        name = f"{slug}.html" if n == 1 else f"{slug}-{n}.html"
        dated = f"{date}-{name}"
        if not os.path.exists(os.path.join(ARTICLES, name)) and \
           not os.path.exists(os.path.join(DRAFTS, dated)):
            return dated
    raise RuntimeError(f"slug 충돌이 너무 많습니다: {slug}")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) != 2:
        sys.exit(__doc__)
    url = argv[1]
    cfg = load_config()

    vid = article.video_id(url)   # 잘못된 URL이면 여기서 바로 멈춘다

    # 출처 표기는 유튜브에서 직접 가져온다 (LLM은 채널명·연도를 지어낸다)
    meta = youtube.fetch_meta(vid)
    print(f"영상: {meta['channel']} — {meta['title']}")
    print("Gemini에게 읽히는 중... (수 분 걸릴 수 있음)")

    fields, usage = gemini.write_article(cfg, url)

    if fields.get("title") == "영상 접근 불가":
        sys.exit("Gemini가 이 영상을 볼 수 없습니다. 비공개·연령제한 영상일 수 있습니다.")

    fields["slug"] = article.clean_slug(fields["slug"])
    fields["source_title"] = youtube.source_title(meta)
    html_text = article.render(fields, url)   # 카테고리·태그 검증 포함

    os.makedirs(DRAFTS, exist_ok=True)
    today = datetime.date.today().isoformat()
    filename = unique_slug(fields["slug"], today)
    path = os.path.join(DRAFTS, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_text)

    print()
    print(f"  카테고리 : {fields['category']}")
    print(f"  제목     : {fields['title']}")
    print(f"  라벨     : {fields['eyebrow']} · {fields['read_minutes']}분 읽기")
    print(f"  원본     : {fields['source_title']}")
    print(f"  토큰     : {usage.get('promptTokenCount')} "
          f"(응답 {usage.get('candidatesTokenCount')})")
    print()
    print(f"초안 생성: {path}")
    print("브라우저로 열어 검수하세요. 카테고리가 틀렸으면 fs:category 한 줄만 고치면 됩니다.")


if __name__ == "__main__":
    main(sys.argv)
