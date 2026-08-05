# -*- coding: utf-8 -*-
"""발행한 기사를 텔레그램 그룹에 게시한다.

    py -3 telegram.py               방금 커밋된 기사로 보낼 메시지를 미리 본다 (전송 안 함)
    py -3 telegram.py --send        실제 전송
    py -3 telegram.py --send <slug> 슬러그를 직접 지정
    py -3 telegram.py --chats       chat_id 확인 (봇을 그룹에 넣고 아무 말이나 한 뒤 실행)

**어떤 기사를 보낼지는 git에서 가져온다.** HEAD 커밋에서 articles/ 에 새로 *추가된*
파일이 곧 방금 발행한 기사다. 별도 상태 파일을 두면 push와 어긋날 수 있어서 이렇게 했다.

링크가 살아 있어야 하므로 **git push 뒤에** 실행한다. run_daily.bat 이 그 순서로 부른다.

**경제·암호화폐만 보낸다.** 사이트에는 6종을 다 올리지만 채널 성격에 맞춰 거른다.
바꾸려면 config 의 telegram_categories. 슬러그를 직접 주면 필터를 건너뛴다.

config.json:
    telegram_bot_token   @BotFather 에서 받은 토큰
    telegram_chat_id     보낼 그룹·채널 (음수 정수 문자열). --chats 로 확인한다.
    telegram_categories  보낼 카테고리 목록. 없으면 경제·암호화폐.
토큰이나 chat_id 가 없으면 조용히 건너뛴다 — 알림이 없다고 발행이 실패하면 안 된다.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARTICLES = os.path.join(ROOT, "articles")

SITE = "https://factorysignal-magazine.vercel.app"
API = "https://api.telegram.org/bot{token}/{method}"

EMOJI = {"정치": "🏛", "경제": "📈", "암호화폐": "₿", "스포츠": "⚽",
         "세계": "🌍", "스타트업": "🚀"}

# 채널에 보낼 카테고리. 사이트에는 6종을 다 올리지만 채널 성격상 이 둘만 보낸다.
# config.json 의 telegram_categories 로 바꾼다. 슬러그를 직접 지정하면 필터를 건너뛴다
# — 사람이 이름을 대고 부른 것은 의도한 것이다.
DEFAULT_CATEGORIES = ("경제", "암호화폐")


def load_config():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def call(cfg, method, **params):
    """Bot API 호출. 실패는 예외로 올린다 — 부르는 쪽에서 삼킬지 결정한다."""
    url = API.format(token=cfg["telegram_bot_token"], method=method)
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def new_article_slugs():
    """HEAD 커밋에서 articles/ 에 새로 추가된 한국어 기사 슬러그."""
    out = subprocess.run(
        ["git", "show", "--name-only", "--diff-filter=A", "--pretty=format:",
         "HEAD", "--", "articles"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    slugs = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if not line.endswith(".html"):
            continue
        name = os.path.basename(line)[:-5]
        if name == "index" or name.endswith("-en"):
            continue        # 영어판은 한국어 기사 메시지에 링크로 넣는다
        slugs.append(name)
    return slugs


def chats_from_updates(updates):
    """getUpdates 응답에서 {chat_id: 이름}.

    봇이 그룹에 초대되면 텔레그램이 my_chat_member 를 보낸다. 이 이벤트는 Group
    Privacy 를 켜둔 채로도 오므로, chat_id 를 얻기 위해 봇에게 그룹 대화 전체를
    읽는 권한을 줄 필요가 없다. message 는 폴백이다.
    """
    seen = {}
    for u in updates:
        for key in ("my_chat_member", "chat_member", "message", "channel_post"):
            c = (u.get(key) or {}).get("chat")
            if c:
                seen[c["id"]] = c.get("title") or c.get("username") or c.get("type")
                break
    return seen


def escape(text):
    """텔레그램 HTML parse_mode 에서 뜻이 있는 문자만 막는다."""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def message(meta, slug, has_en=False):
    """게시할 메시지 본문. 순수 함수라 전송 없이 테스트한다."""
    cat = meta.get("category") or ""
    head = f"{EMOJI.get(cat, '📰')} {cat}"
    read = str(meta.get("read") or "")
    if read:
        # fs:read 는 숫자만 들어 있다("4"). 채팅에서는 단위가 있어야 읽힌다.
        head += f" · {read}분 읽기" if read.isdigit() else f" · {read}"
    lines = [head, f"<b>{escape(meta['title'])}</b>"]
    # eyebrow 는 영문 키커("Crypto Policy")라 채팅에 도움이 안 된다. 한국어 요약을 쓴다.
    summary = meta.get("description") or meta.get("eyebrow")
    if summary:
        lines.append(escape(summary))
    lines.append(f"{SITE}/articles/{slug}.html")
    if has_en:
        lines.append(f'<a href="{SITE}/articles/{slug}-en.html">English</a>')
    return "\n\n".join(lines[:2]) + "\n" + "\n".join(lines[2:])


def post(cfg, meta, slug, has_en=False):
    return call(cfg, "sendMessage",
                chat_id=cfg["telegram_chat_id"],
                text=message(meta, slug, has_en),
                parse_mode="HTML",
                disable_web_page_preview="false")


def allowed(cfg, category):
    return category in (cfg.get("telegram_categories") or DEFAULT_CATEGORIES)


def configured(cfg):
    return bool(cfg.get("telegram_bot_token") and cfg.get("telegram_chat_id"))


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    sys.path.insert(0, HERE)
    import publish

    send = "--send" in argv
    cfg = load_config()

    if "--chats" in argv:
        if not cfg.get("telegram_bot_token"):
            print("config.json 에 telegram_bot_token 이 없습니다.")
            return 1
        found = chats_from_updates(call(cfg, "getUpdates").get("result", []))
        if not found:
            print("아직 어느 그룹에서도 신호가 오지 않았습니다.")
            print("텔레그램에서 봇 프로필 → '그룹에 추가' 로 그룹에 넣은 뒤 다시 실행하세요.")
            return 1
        for cid, title in found.items():
            print(f"  telegram_chat_id: {cid}    {title}")
        return 0

    named = [a for a in argv[1:] if not a.startswith("-")]
    slugs = named or new_article_slugs()
    if not slugs:
        print("HEAD 커밋에 새 기사가 없습니다. 보낼 것이 없습니다.")
        return 0

    if send and not configured(cfg):
        print("telegram_bot_token / telegram_chat_id 가 없어 건너뜁니다.")
        return 0

    fails = 0
    for slug in slugs:
        path = os.path.join(ARTICLES, slug + ".html")
        if not os.path.exists(path):
            print(f"  없음: {slug}.html")
            fails += 1
            continue
        meta = publish.read_meta(path)
        if not named and not allowed(cfg, meta["category"]):
            print(f"  건너뜀 [{meta['category']}] {slug} — 채널 대상 카테고리가 아님")
            continue
        has_en = os.path.exists(os.path.join(ARTICLES, slug + "-en.html"))
        if not send:
            print("─" * 60)
            print(re.sub(r"<[^>]+>", "", message(meta, slug, has_en)))
            continue
        try:
            post(cfg, meta, slug, has_en)
            print(f"  전송: [{meta['category']}] {meta['title'][:44]}")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            body = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    body = e.read().decode("utf-8", "replace")[:200]
                except Exception:
                    pass
            print(f"  실패: {slug} — {e} {body}")
            fails += 1

    if not send:
        print("─" * 60)
        print(f"미리보기 {len(slugs)}건. 실제로 보내려면 --send")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
