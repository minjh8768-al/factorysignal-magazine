# -*- coding: utf-8 -*-
"""API 없이 돌리는 본문 이상 검사. 순수 함수라 빠르고 테스트가 쉽다.

자동 발행의 게이트로 쓴다. 사람이 읽어서 잡던 것 중 기계로 판정 가능한 것만 모았다.
여기서 걸리면 그 기사는 발행하지 않고 보류한다.

잡을 수 없는 것도 분명히 해둔다. "이름은 맞지만 지금 그 자리가 아닌" 오류
(현 연준 의장을 파월로 씀)는 어떤 규칙으로도 판정되지 않는다. 그건 사람 몫이다.
"""
import datetime
import re

# LLM이 흘리는 상용구. 이것만으로 LLM이 확실한 것들이다.
BOILERPLATE = (
    "저는 AI", "언어 모델", "제공된 영상", "영상에 따르면 제가",
    "제공해 주신", "확인할 수 없습니다",
    "as an ai", "i cannot", "i'm sorry", "based on the provided",
)

# 사과·안내 어투는 영상 속 실제 발언과 겹친다. 실측: 축구협회 혁신위 기사에서
# "축구인의 한 명으로서 이 자리가 죄송스럽기도 하고"라는 인용이 '죄송'에 걸려 보류됐다.
# 그래서 이 어투는 '도움을 못 준다'는 진술과 같이 나올 때만 상용구로 본다.
# 이전에 있던 "다음은"("다음은 발언 요지다")도 같은 이유로 뺐다.
APOLOGY = re.compile(r"죄송|양해 ?바|요청하신|말씀드릴 수 없")
INABILITY = re.compile(
    r"확인할 수 없|알 수 없|정보가 없|제공되지 않|포함되어 있지 않"
    r"|도움을 드릴|답변을 드릴|요약할 수 없|볼 수 ?없|볼 수가 없")

# 본문이 이보다 짧으면 생성이 덜 된 것으로 본다 (실측 기사들은 1,300~3,000자)
MIN_BODY_CHARS = 700

# 연도는 현재를 기준으로 이 범위를 벗어나면 확인 대상
YEAR_BACK, YEAR_FORWARD = 80, 3

RE_SENT = re.compile(r"[^.!?…]{12,}[.!?…]")
RE_PERCENT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*%")
RE_YEAR = re.compile(r"(?<!\d)((?:1[89]|20)\d\d)\s*년")
RE_TAG = re.compile(r"<[^>]+>")


def plain(body_html):
    return re.sub(r"\s+", " ", RE_TAG.sub(" ", body_html)).strip()


def find_boilerplate(text):
    """영어 상용구는 대소문자를 무시하고, 한국어는 그대로 찾는다."""
    low = text.lower()
    found = []
    for p in BOILERPLATE:
        haystack = low if p.isascii() else text
        needle = p.lower() if p.isascii() else p
        if needle in haystack:
            found.append(p)
    a, i = APOLOGY.search(text), INABILITY.search(text)
    if a and i:
        found.append(f"{a.group(0)}…{i.group(0)}")
    return found


def find_repeated_sentences(text, min_len=20):
    """같은 문장이 두 번 이상. LLM이 루프에 빠지면 이렇게 된다."""
    seen, dup = {}, []
    for s in RE_SENT.findall(text):
        s = s.strip()
        if len(s) < min_len:
            continue
        seen[s] = seen.get(s, 0) + 1
    return [s for s, n in seen.items() if n > 1]


def find_implausible_percent(text, limit=100):
    """비율이 100%를 크게 넘으면 확인 대상. 증가율은 넘을 수 있어 여유를 둔다."""
    out = []
    for m in RE_PERCENT.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if v > limit * 10:            # 1000% 초과는 사실상 오기
            out.append(m.group(0))
    return out


def find_odd_years(text, today=None):
    """현재 기준 범위를 벗어난 연도. 역사 기사가 아니면 대개 오기다."""
    now = (today or datetime.date.today()).year
    lo, hi = now - YEAR_BACK, now + YEAR_FORWARD
    return sorted({m.group(1) for m in RE_YEAR.finditer(text)
                   if not (lo <= int(m.group(1)) <= hi)})


def find_unclosed_quote(text):
    """따옴표 개수가 홀수면 인용이 잘렸을 수 있다."""
    odd = []
    straight = text.count('"')
    curly_open, curly_close = text.count("“"), text.count("”")
    if straight % 2:
        odd.append(f'따옴표(") {straight}개 — 홀수')
    if curly_open != curly_close:
        odd.append(f"곡선 따옴표 {curly_open}/{curly_close} — 짝이 안 맞음")
    return odd


def check(body_html, today=None):
    """[(심각도, 항목, 내용)] 을 반환한다. 심각도 '!!' 는 자동 발행을 막는다."""
    text = plain(body_html)
    issues = []

    if len(text) < MIN_BODY_CHARS:
        issues.append(("!!", "분량", f"본문 {len(text)}자 — {MIN_BODY_CHARS}자 미만"))
    for p in find_boilerplate(text):
        issues.append(("!!", "상용구", f"'{p}' 가 본문에 있음"))
    for s in find_repeated_sentences(text):
        issues.append(("!!", "문장중복", s[:60]))
    for p in find_implausible_percent(text):
        issues.append(("!!", "수치", f"{p} — 값이 비현실적"))
    for y in find_odd_years(text, today):
        issues.append(("??", "연도", f"{y}년 — 현재 기준 범위 밖"))
    for q in find_unclosed_quote(text):
        issues.append(("??", "인용부호", q))
    return issues


def blocking(issues):
    return [i for i in issues if i[0] == "!!"]
