# -*- coding: utf-8 -*-
"""유튜브 URL -> 검수용 기사 초안 HTML.

    py -3 draft.py https://youtu.be/xxxxxxxxxxx
    py -3 draft.py <url1> <url2> <url3> ...      여러 개를 동시에 처리

_drafts/YYYY-MM-DD-<slug>.html 을 만든다. articles/ 는 건드리지 않는다.
브라우저로 그 파일을 열어 검수한 뒤 발행한다.

여러 URL은 최대 3개씩 동시에 돌린다. 순차로 6편을 만들면 12~15분이 걸리는데
동시 처리하면 3~4분으로 줄어든다. 3개로 제한한 이유는 Gemini 무료 티어의 분당
요청 한도 때문이고, 429가 나면 gemini.py가 서버가 알려준 시간만큼 기다려 재시도한다.
"""
import datetime
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import article
import gemini
import youtube

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DRAFTS = os.path.join(ROOT, "_drafts")
ARTICLES = os.path.join(ROOT, "articles")

MAX_PARALLEL = 3

# 파일명 결정과 쓰기는 한 번에 하나씩. 동시에 하면 두 스레드가 같은 이름을 잡는다.
_write_lock = threading.Lock()
_print_lock = threading.Lock()


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


def say(*lines):
    with _print_lock:
        for line in lines:
            print(line)
        sys.stdout.flush()


def make_draft(cfg, url, today):
    """URL 하나를 초안 파일로. 성공하면 결과 dict, 실패하면 예외를 담아 반환."""
    try:
        vid = article.video_id(url)
        meta = youtube.fetch_meta(vid)
        say(f"[{vid}] {meta['channel']} — {meta['title'][:60]}")

        fields, usage = gemini.write_article(cfg, url)
        if fields.get("title") == "영상 접근 불가":
            raise RuntimeError("Gemini가 이 영상을 볼 수 없습니다 "
                               "(비공개·연령제한일 수 있음).")

        fields["slug"] = article.clean_slug(fields["slug"])
        fields["source_title"] = youtube.source_title(meta)
        html_text = article.render(fields, url)   # 카테고리·태그·잘림 검증 포함

        with _write_lock:
            os.makedirs(DRAFTS, exist_ok=True)
            filename = unique_slug(fields["slug"], today)
            path = os.path.join(DRAFTS, filename)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(html_text)

        say(f"[{vid}] 완료 [{fields['category']}] {filename}",
            f"        {fields['title'][:70]}",
            f"        토큰 {usage.get('promptTokenCount')}")
        return {"url": url, "path": path, "fields": fields, "usage": usage}
    except Exception as e:
        say(f"[{url[-11:]}] 실패: {e}")
        return {"url": url, "error": e}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    urls = [a for a in argv[1:] if not a.startswith("--")]
    if not urls:
        sys.exit(__doc__)
    cfg = load_config()
    today = datetime.date.today().isoformat()

    # 잘못된 URL은 Gemini를 부르기 전에 걸러낸다
    for url in urls:
        article.video_id(url)

    if len(urls) == 1:
        results = [make_draft(cfg, urls[0], today)]
    else:
        print(f"{len(urls)}건을 최대 {MAX_PARALLEL}개씩 동시에 처리합니다. "
              "(각 1~2분, 순차보다 3~4배 빠름)\n")
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            results = list(pool.map(lambda u: make_draft(cfg, u, today), urls))

    ok = [r for r in results if "path" in r]
    bad = [r for r in results if "error" in r]
    total_tokens = sum(r["usage"].get("promptTokenCount", 0) for r in ok)

    print(f"\n성공 {len(ok)}건 / 실패 {len(bad)}건  ·  총 토큰 {total_tokens:,}")
    if bad:
        print("실패한 건은 그냥 다시 실행하면 대개 됩니다 "
              "(태그 짝 검사에 걸리는 경우가 있습니다).")
    if ok:
        print("\n다음 단계:")
        print("  py -3 factcheck.py --write   네이버 뉴스로 고유명사·수치 대조")
        print("  run_preview.bat              브라우저로 검수")
        print("  py -3 publish.py --apply     발행")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
