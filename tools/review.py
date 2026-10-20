# -*- coding: utf-8 -*-
"""초안 승인 후 발행 (2026-10-20, 사용자 결정 'B: AI가 쓰고, 사람이 승인하고, 발행').

    py -3 review.py --send              _drafts/ 의 초안을 비공개 저장소(Upstash)에 넣고
                                        관리자 텔레그램으로 [발행]/[보류] 버튼과 함께 보낸다
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


def send(cfg):
    files = sorted(glob.glob(os.path.join(DRAFTS, "*.html")))
    if not files:
        print("승인 보낼 초안이 없습니다.")
        return 0
    sent = 0
    for path in files:
        m = DATE_PREFIX.match(os.path.basename(path))
        if not m:
            continue
        date, slug = m.groups()
        with open(path, encoding="utf-8") as f:
            text = f.read()
        redis(cfg, [["SET", f"draft:{slug}", json.dumps({"date": date, "html": text}), "EX", DRAFT_TTL]])
        keyboard = {"inline_keyboard": [[{"text": "✅ 발행", "callback_data": f"pub:{slug}"},
                                         {"text": "⏸ 보류", "callback_data": f"skip:{slug}"}]]}
        photo = _meta(text, "fs:photo")
        if photo:   # 사진이 기사와 맞는지 같이 보도록 먼저 보낸다 (실패해도 계속)
            try:
                telegram(cfg, "sendPhoto", chat_id=cfg["telegram_admin_chat_id"], photo=photo)
            except Exception:
                pass
        telegram(cfg, "sendMessage", chat_id=cfg["telegram_admin_chat_id"], text=review_message(text, slug),
                 parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
        sent += 1
    print(f"승인 요청 {sent}편 보냄")
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
    need = ("telegram_bot_token", "telegram_admin_chat_id", "kv_rest_api_url", "kv_rest_api_token")
    missing = [k for k in need if not cfg.get(k)]
    if missing:
        print(f"승인 기능 설정이 없습니다: {missing} — 초안은 _drafts/ 와 실행 기록(artifact)에만 남습니다.")
        return 0
    if "--send" in argv:
        return send(cfg)
    if "--publish" in argv:
        return publish_one(cfg, argv[argv.index("--publish") + 1])
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
