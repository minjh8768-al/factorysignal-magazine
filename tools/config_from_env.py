# -*- coding: utf-8 -*-
"""환경변수로 tools/config.json 을 만든다. GitHub Actions 러너에서만 쓴다.

config.json 은 gitignore 라 저장소에 없다. 러너에서는 저장소 시크릿이 환경변수로
들어오므로 그것을 모아 같은 모양의 파일을 만든다. 나머지 코드는 파일만 보므로
로컬에서 돌 때와 똑같이 동작한다.

값은 절대 출력하지 않는다 — 공개 저장소라 실행 로그가 누구에게나 보인다.
GitHub 이 시크릿을 가려 주기는 하지만, 애초에 찍지 않는 편이 안전하다.

    py -3 config_from_env.py           tools/config.json 생성
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 비밀값. 환경변수 이름 -> config 키
SECRETS = {
    "GEMINI_API_KEY": "gemini_api_key",
    "NAVER_CLIENT_ID": "naver_client_id",
    "NAVER_CLIENT_SECRET": "naver_client_secret",
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
    "TELEGRAM_CHAT_ID": "telegram_chat_id",
    "ECOS_API_KEY": "ecos_api_key",
    "PEXELS_API_KEY": "pexels_api_key",
}

# JSON 목록으로 들어오는 것
JSON_SECRETS = {"GEMINI_API_KEYS": "gemini_api_keys"}

# 비밀이 아니라 저장소에 둬도 되는 설정. 로컬 config.json 과 같은 값이어야 한다.
PUBLIC = {
    "gemini_model": "gemini-3.6-flash",
    "media_resolution": "MEDIA_RESOLUTION_LOW",
    "telegram_categories": ["경제", "암호화폐"],
}

# 이것들이 없으면 파이프라인이 아예 돌지 않는다.
REQUIRED = ("gemini_api_key", "naver_client_id", "naver_client_secret")


def build(env=None):
    env = os.environ if env is None else env
    cfg = dict(PUBLIC)
    for name, key in SECRETS.items():
        v = (env.get(name) or "").strip()
        if v:
            cfg[key] = v
    for name, key in JSON_SECRETS.items():
        raw = (env.get(name) or "").strip()
        if not raw:
            continue
        try:
            got = json.loads(raw)
        except ValueError:
            got = [s.strip() for s in raw.split(",") if s.strip()]
        if isinstance(got, list) and got:
            cfg[key] = got
    return cfg


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = build()

    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        print(f"필수 시크릿이 없습니다: {missing}")
        print("저장소 Settings > Secrets and variables > Actions 에서 등록하세요.")
        return 1

    path = os.path.join(HERE, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    # 이름과 유무만 보고한다. 값은 찍지 않는다.
    print("config.json 생성:")
    for k, v in cfg.items():
        if isinstance(v, list):
            state = f"{len(v)}개"
        elif k in ("gemini_model", "media_resolution"):
            state = v
        else:
            state = "설정됨" if v else "없음"
        print(f"  {k:22} {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
