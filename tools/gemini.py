# -*- coding: utf-8 -*-
"""Gemini 호출. 유튜브 URL을 fileData로 직접 넘겨 영상을 읽힌다.

HTML도 기사도 모른다. 프롬프트를 받아 구조화된 JSON 딕셔너리를 반환한다.
"""
import json
import re
import time
import urllib.error
import urllib.request

from article import CATEGORIES

ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent?key={key}")

# Gemini가 반드시 이 모양으로 반환하도록 강제한다 (JSON 파싱 실패를 구조적으로 없앤다)
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
        "slug": {"type": "STRING"},
        "category": {"type": "STRING", "enum": list(CATEGORIES)},
        "eyebrow": {"type": "STRING"},
        "read_minutes": {"type": "INTEGER"},
        "body_html": {"type": "STRING"},
    },
    "required": ["title", "description", "slug", "category", "eyebrow",
                 "read_minutes", "body_html"],
    "propertyOrdering": ["title", "description", "slug", "category", "eyebrow",
                         "read_minutes", "body_html"],
}

PROMPT = f"""너는 한국어 시사 매거진 Factory Magazine의 기자다.
첨부된 유튜브 영상을 보고, 그 내용을 정리한 기사 한 편을 쓴다.

절대 규칙:
- 문체는 '~다' 평서체로 쓴다(뉴스 기사체). 영상 화자가 존댓말이나 구어체를 써도
  기사 본문은 평서체다. 단, blockquote 안의 직접 인용은 화자가 말한 그대로 옮긴다.
- 영상에서 실제로 말한 내용만 근거로 삼는다. 영상에 없는 사실·수치·날짜를 채우지 마라.
- 사람 이름·회사명·직함·기관명이 또렷하게 들리지 않으면 아예 쓰지 마라.
  "한 평론가는", "이 회사는"처럼 일반 명사로 돌려 쓴다. 잘못 적는 것보다 낫다.
- 숫자도 마찬가지다. 확실하지 않은 수치는 쓰지 말고 "크게 웃돌았다"처럼 서술한다.
- 확실하지 않으면 쓰지 마라. 분량을 늘리려 추측하지 마라.
- 날짜와 채널명은 아예 쓰지 마라. 출처 표기는 코드가 따로 붙인다.
- 모든 평가·전망은 그 말을 한 사람에게 귀속시킨다. "우려가 깊어지고 있다",
  "평가가 나온다"처럼 주체를 숨긴 표현을 쓰지 마라.
  대신 "A는 ...라고 우려했다", "B는 ...라고 평가했다"로 쓴다.
- 특정 정당·인물을 편드는 논평을 쓰지 마라. 누가 무엇을 주장했는지만 서술한다.
- 영상이 한국어가 아니면, 인용은 원문과 번역을 나란히 쓴다. 원문 언어 코드를 lang에 넣는다.
  <blockquote lang="en">We are not going to change the 2 percent target.</blockquote>
  <p class="quote-tr">"2% 목표를 바꾸지 않겠습니다."</p>
  원문을 함께 실으면 독자가 번역을 검증할 수 있다. 한국어 영상이면 blockquote 하나만 쓴다.
- blockquote에는 화자가 실제로 한 발언만 그대로 옮긴다. 요약문을 인용문처럼 만들지 마라.
  인용문은 2~3문장 이내로 짧게 자른다. 인용문 안에 화자 이름이나 "…라고 말했다" 같은
  서술을 넣지 마라. 발언 본문만 넣고, 누가 말했는지는 인용문 바로 앞 단락에서 밝힌다.
  말줄임표로 서로 떨어진 발언을 이어 붙이지 마라.
  내레이션만 있고 말하는 사람이 없는 영상이라면 blockquote를 하나도 쓰지 마라.
  기자의 해설을 인용문처럼 감싸는 것은 금지다.

각 필드:
- title: 기사 제목. 영상 제목을 그대로 베끼지 말고 핵심을 담아 다시 쓴다.
  핵심 발언을 큰따옴표로 인용해 넣는 형태를 선호한다.
- description: 검색결과에 뜨는 한 문장 요약 (80~140자).
- slug: 영문 소문자와 하이픈만 쓴 파일명 (3~6단어). 예: assembly-investigation-power-bill
- category: 다음 중 정확히 하나. {" / ".join(CATEGORIES)}
  국내 정당·국회·정부 문제는 정치. 해외 정세·국제관계는 세계.
  금리·물가·산업·기업 실적은 경제. 가상자산·블록체인은 암호화폐.
  창업·스타트업·투자유치는 스타트업.
- eyebrow: 기사 상단과 카드에 붙는 영문 라벨 2~3단어. 쉼표나 마침표를 넣지 마라.
  예: Politics / Market Watch / Policy Watch / World Affairs / Startup Insights
- read_minutes: 본문 분량에 맞는 읽기 시간 (정수, 3~10)
- body_html: 본문. 아래 태그만 쓴다.
  <p> 단락, <h2> 소제목, <blockquote> 직접 인용, <ul><li> 목록, <strong> 강조
  외국어 인용에는 <blockquote lang="en"> 과 <p class="quote-tr"> 를 쓴다.
  구조: 도입 단락 -> <h2> 소제목으로 나눈 3~6개 섹션 -> 각 섹션에 단락 1~3개.
  적절한 곳에 <blockquote> 1~2개를 넣는다. 마지막은 정리 섹션.
  <h1>, <div>, <script>, <style>, <img>, 인라인 style 속성은 쓰지 마라.
  마크다운을 쓰지 마라. HTML 태그만 쓴다.
영상을 볼 수 없으면 title을 정확히 "영상 접근 불가"로 채워라."""


def _post(url, payload, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _retry_delay(message, default):
    """서버가 알려준 재시도 대기시간(초)을 뽑는다."""
    m = re.search(r'"retryDelay"\s*:\s*"(\d+)s"', message)
    return min(int(m.group(1)), 35) if m else default


def write_article(cfg, youtube_url, timeout=600, retries=3):
    """유튜브 URL을 보고 기사 필드 딕셔너리를 반환한다."""
    payload = {
        "contents": [{
            "parts": [
                {"fileData": {"fileUri": youtube_url}},
                {"text": PROMPT},
            ]
        }],
        "generationConfig": {
            "mediaResolution": cfg.get("media_resolution", "MEDIA_RESOLUTION_LOW"),
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            # 기본값으로는 본문이 문장 중간에서 잘린다 (사고 토큰이 출력 예산을 함께 쓴다)
            "maxOutputTokens": cfg.get("max_output_tokens", 32768),
        },
    }
    url = ENDPOINT.format(model=cfg["gemini_model"], key=cfg["gemini_api_key"])

    last = ""
    for attempt in range(retries):
        try:
            data = _post(url, payload, timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            last = f"HTTP {e.code}: {body[:400]}"
            if e.code in (429, 503) and attempt < retries - 1:
                wait = _retry_delay(body, 10 * (attempt + 1))
                print(f"  Gemini {e.code} — {wait}초 후 재시도 "
                      f"({attempt + 1}/{retries - 1})")
                time.sleep(wait)
                continue
            if e.code == 429:
                raise RuntimeError(
                    "Gemini 무료 한도를 다 썼습니다. 잠시 후 다시 시도하거나 "
                    "config.json의 gemini_model을 바꾸세요.\n" + last
                )
            raise RuntimeError(last)
        except urllib.error.URLError as e:
            last = f"연결 실패: {e.reason}"
            if attempt < retries - 1:
                time.sleep(5)
                continue
            raise RuntimeError(last)

        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini가 빈 응답을 보냈습니다: {str(data)[:400]}")

        # 잘린 응답을 절대 통과시키지 않는다. 구조화 출력 모드는 상한에 걸려도 JSON을
        # 닫아버려서 파싱은 성공하고 본문만 문장 중간에서 끊긴다.
        reason = candidates[0].get("finishReason")
        if reason not in (None, "STOP"):
            raise RuntimeError(
                f"Gemini 응답이 정상 종료되지 않았습니다 (finishReason={reason}). "
                "본문이 잘렸을 수 있어 중단합니다. MAX_TOKENS이면 config.json의 "
                "max_output_tokens를 올리세요."
            )

        text = "".join(
            p.get("text", "")
            for p in candidates[0].get("content", {}).get("parts", [])
        )
        usage = data.get("usageMetadata", {})
        return json.loads(text), usage

    raise RuntimeError(last or "Gemini 호출 실패")
