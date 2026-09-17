# -*- coding: utf-8 -*-
"""분석 기사가 투자자문으로 읽히지 않는지 검사한다. API 없는 순수 함수다.

왜 필요한가
    자본시장법상 유사투자자문업은 '불특정 다수인을 대상으로 대가를 받고 금융투자
    상품의 투자판단에 관한 자문을 하는 것'이다. 시장을 보도·해설하는 것은 여기에
    들어가지 않지만, 같은 글에 "매수", "목표가", "지금이 기회" 한 줄이 섞이면
    성격이 달라진다. 그 한 줄을 사람 눈에 맡기지 않기 위한 검사다.

    법률 자문이 아니다. 명백한 것을 기계적으로 막는 장치이고, 최종 판단은 사람이 한다.

무엇을 막는가
    ADVICE   특정 행동을 권하는 말. 무조건 차단한다.
    PROMISE  수익·원금을 보장하는 말. 무조건 차단한다.
    FUTURE   조건 없이 단정하는 미래형. 같은 문장에 가정이 없으면 차단한다.
             ("금리가 동결되면 ~라는 해석이 가능하다" 는 통과, "환율은 오를 것이다" 는 차단)
"""
import re

# 행동을 권하는 말. 기사에 한 번이라도 나오면 자문으로 읽힌다.
ADVICE = (
    "매수", "매도", "사야", "팔아야", "담아야", "줍줍", "손절", "익절",
    "비중 확대", "비중 축소", "비중을 늘", "비중을 줄", "진입 시점", "포지션",
    "추천", "유망", "최선호", "탑픽", "top pick", "주목할 종목", "관심 종목",
    "목표가", "목표주가", "적정주가", "적정 주가",
    "지금이 기회", "막차", "저점 매수", "고점 매도", "분할 매수",
    "투자 전략", "포트폴리오 구성", "대응 전략",
)

# 결과를 약속하는 말.
PROMISE = (
    "원금 보장", "수익 보장", "수익률 보장", "확실한 수익", "반드시 오른",
    "반드시 상승", "무조건 오른", "손실 없", "안전한 투자",
)

# 미래를 말하는 어미. 같은 문장에 가정이 없으면 단정으로 본다.
FUTURE = re.compile(
    r"것이다|것으로 보인다|할 전망|전망이다|예상된다|예측된다|기대된다"
    r"|오를 것|내릴 것|상승할|하락할|급등할|급락할")

# 가정을 나타내는 표시. 이게 있으면 조건부 서술로 본다.
CONDITION = re.compile(
    r"면 |면,|하면|한다면|경우|가정|조건|시나리오|~라면|일 때|없다면|된다면")

# 발행 전에 반드시 본문에 있어야 하는 문구.
REQUIRED_DISCLAIMER = ("투자 조언이나 권유가 아니", "본인의 판단과 책임")

RE_TAG = re.compile(r"<[^>]+>")
RE_SENT = re.compile(r"[^.!?…]+[.!?…]")


def plain(html_text):
    return re.sub(r"\s+", " ", RE_TAG.sub(" ", html_text)).strip()


def find_advice(text):
    return [w for w in ADVICE if w in text]


def find_promise(text):
    return [w for w in PROMISE if w in text]


def find_bare_future(text):
    """조건 없이 미래를 단정한 문장.

    미래 언급 자체를 막으면 기사를 쓸 수 없다. 가정을 밝혔는지만 본다.
    """
    out = []
    for s in RE_SENT.findall(text):
        s = s.strip()
        if FUTURE.search(s) and not CONDITION.search(s):
            out.append(s[:70])
    return out


def check(body_html, title="", disclaimer=""):
    """[(심각도, 항목, 내용)]. '!!' 는 발행을 막는다."""
    text = plain(body_html)
    issues = []

    for w in find_advice(text + " " + title):
        issues.append(("!!", "투자권유", f"'{w}' — 행동을 권하는 표현"))
    for w in find_promise(text + " " + title):
        issues.append(("!!", "수익보장", f"'{w}' — 결과를 약속하는 표현"))
    for s in find_bare_future(text):
        issues.append(("!!", "단정적 예측", f"가정 없이 미래를 단정: {s}"))

    if disclaimer:
        missing = [p for p in REQUIRED_DISCLAIMER if p not in disclaimer]
        if missing:
            issues.append(("!!", "고지 누락", f"면책 문구에 없음: {missing}"))
    return issues


def blocking(issues):
    return [i for i in issues if i[0] == "!!"]
