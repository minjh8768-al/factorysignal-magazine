# -*- coding: utf-8 -*-
"""초안 승인 후 발행 (2026-10-20, 사용자 결정 'B: AI가 쓰고, 사람이 승인하고, 발행').

    py -3 review.py --send              _drafts/ 의 초안을 비공개 저장소(Upstash)에 넣고
                                        관리자 페이지(/admin.html) 승인 대기로 올린다
    py -3 review.py --publish <slug>    저장소의 초안을 꺼내 발행한다 (승인 버튼 → GitHub 워크플로)

왜 저장소(Upstash)에 두나
    GitHub 저장소가 공개라서, 승인 전 초안(오류가 있을 수 있는 글)을 커밋하면 누구나 볼 수
    있다. 투표·구독과 같은 Upstash Redis 에 7일간 보관한다.

config.json (GitHub 에서는 비밀값 → config_from_env.py):
    telegram_bot_token, telegram_admin_chat_id   승인 메시지를 받을 관리자 개인 대화
    kv_rest_api_url, kv_rest_api_token          Upstash REST
"""
import glob
import html
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DRAFTS = os.path.join(ROOT, "_drafts")
SITE = "https://factorysignal-magazine.vercel.app/articles/"
DRAFT_TTL = 7 * 24 * 3600
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.html$")


def load_config():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def redis(cfg, commands):
    req = urllib.request.Request(cfg["kv_rest_api_url"].rstrip("/") + "/pipeline",
                                 data=json.dumps(commands).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + cfg["kv_rest_api_token"],
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return [x.get("result") for x in json.loads(r.read().decode("utf-8"))]


def telegram(cfg, method, **params):
    req = urllib.request.Request(f"https://api.telegram.org/bot{cfg['telegram_bot_token']}/{method}",
                                 data=json.dumps(params).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _meta(text, name):
    m = re.search(r'<meta name="%s" content="([^"]*)"' % re.escape(name), text)
    return html.unescape(m.group(1)) if m else ""


def plain_body(text):
    """기사 본문을 텔레그램용 일반 글로 (태그 제거, 문단 유지)."""
    body = text.split('<article class="article-content">', 1)[-1].split("</article>", 1)[0]
    body = re.sub(r'<div class="video-embed">.*?</div>', "", body, flags=re.S)
    body = re.sub(r'<p class="source-note">.*?</p>', "", body, flags=re.S)
    body = re.sub(r'<div class="disclaimer">.*?</div>', "", body, flags=re.S)
    body = re.sub(r"<li>", "• ", body)
    body = re.sub(r"<h2>(.*?)</h2>", r"\n■ \1", body)
    body = re.sub(r"</(p|li|h2|blockquote)>", "\n", body)
    body = html.unescape(re.sub(r"<[^>]+>", "", body))
    body = "\n".join(line.strip() for line in body.splitlines())
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def review_message(text, slug):
    title = re.search(r"<title>(.*?)</title>", text, re.S)
    title = html.unescape(title.group(1)).split(" — ")[0] if title else slug
    parts = [f"📝 승인 대기 · {_meta(text, 'fs:category')} · {_meta(text, 'fs:eyebrow')}",
             f"\n<b>{html.escape(title)}</b>"]
    poll = _meta(text, "fs:poll")
    if poll:
        parts.append(f"\n🗳 투표: {html.escape(poll)}")
    credit = _meta(text, "fs:photo_by")
    if credit:
        parts.append(f"📷 사진: {html.escape(credit)} ({html.escape(_meta(text, 'fs:photo_license') or 'Pexels')})")
    parts.append("\n" + html.escape(plain_body(text)))
    vid = _meta(text, "fs:video")
    if vid:
        parts.append(f'\n원본 영상: https://www.youtube.com/watch?v={vid}')
    msg = "\n".join(parts)
    return msg[:3900] + ("…" if len(msg) > 3900 else "")


ADMIN_URL = "https://factorysignal-magazine.vercel.app/admin.html"


def send(cfg):
    """초안을 관리자 페이지(/admin.html '승인 대기')에 올린다. 텔레그램 설정이 있으면 도착 알림만 보낸다.
    (2026-10-20: 텔레그램 버튼 방식 대신 관리자 페이지에서 수정·발행·보류)"""
    files = sorted(glob.glob(os.path.join(DRAFTS, "*.html")))
    if not files:
        print("승인 대기로 올릴 초안이 없습니다.")
        return 0
    titles = []
    for path in files:
        m = DATE_PREFIX.match(os.path.basename(path))
        if not m:
            continue
        date, slug = m.groups()
        with open(path, encoding="utf-8") as f:
            text = f.read()
        redis(cfg, [["SET", f"draft:{slug}", json.dumps({"date": date, "html": text}), "EX", DRAFT_TTL]])
        t = re.search(r"<title>(.*?)</title>", text, re.S)
        titles.append(html.unescape(t.group(1)).split(" — ")[0] if t else slug)
    print(f"승인 대기 {len(titles)}편 올림")
    if cfg.get("telegram_bot_token") and cfg.get("telegram_admin_chat_id") and titles:
        try:
            telegram(cfg, "sendMessage", chat_id=cfg["telegram_admin_chat_id"], disable_web_page_preview=True,
                     text=f"📝 오늘 초안 {len(titles)}편이 승인을 기다려요\n\n"
                          + "\n".join(f"• {t}" for t in titles) + f"\n\n{ADMIN_URL}")
        except Exception:
            pass
    return 0


def publish_one(cfg, slug):
    import publish
    got = redis(cfg, [["GET", f"draft:{slug}"]])[0]
    if not got:
        print(f"저장소에 초안이 없습니다(7일이 지났거나 이미 처리됨): {slug}")
        return 1
    d = json.loads(got)
    os.makedirs(DRAFTS, exist_ok=True)
    with open(os.path.join(DRAFTS, f"{d['date']}-{slug}.html"), "w", encoding="utf-8") as f:
        f.write(d["html"])
    publish.do_publish([slug], True, translate_too=True)
    redis(cfg, [["DEL", f"draft:{slug}"]])
    if cfg.get("telegram_bot_token") and cfg.get("telegram_admin_chat_id"):
        try:
            telegram(cfg, "sendMessage", chat_id=cfg["telegram_admin_chat_id"],
                     text=f"✅ 발행 완료\n{SITE}{slug}.html\n(사이트 반영까지 1~2분)")
        except Exception:
            pass
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cfg = load_config()
    need = ("kv_rest_api_url", "kv_rest_api_token")      # 텔레그램은 선택 (도착 알림만)
    missing = [k for k in need if not cfg.get(k)]
    if missing:
        print(f"승인 대기 저장소 설정이 없습니다: {missing} — 초안은 실행 기록(artifact)에만 남습니다.")
        return 0
    if "--send" in argv:
        return send(cfg)
    if "--publish" in argv:
        return publish_one(cfg, argv[argv.index("--publish") + 1])
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
