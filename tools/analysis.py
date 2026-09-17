# -*- coding: utf-8 -*-
"""데이터 근거 분석 기사(시험). 영상 요약이 아니라 시장 수치가 출발점이다.

    py -3 analysis.py            _drafts/ 에 초안 생성

설계 원칙은 draft.py 와 같다 — **LLM은 문장만 쓴다.**
수치·표·차트는 market.py 가 계산하고 이 파일이 그린다. 프롬프트에는 계산된 값만
넣고 그 밖의 숫자를 쓰지 말라고 명시한다. 기존 파이프라인에서 LLM이 연도와 통계를
지어낸 적이 있어서, 숫자를 만들 기회 자체를 주지 않는 쪽으로 설계했다.

예측은 하지 않는다. 회고(무엇이 얼마나 움직였나)와 조건부 서술(가정을 밝힌
시나리오)까지만 한다. 유사투자자문업 문제도 있고, LLM이 시세를 맞힐 근거도 없다.
"""
import datetime
import glob
import html
import json
import os
import re
import sys

import agenda
import article
import compliance
import ecos
import pexels
import gemini
import market

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DRAFTS = os.path.join(ROOT, "_drafts")

# 계획 없이 그냥 돌릴 때의 기본값. (심볼, 이름, 소스, 단위, 색) — agenda 와 같은 순서다.
DEFAULT_INDICATORS = [
    ("^KS11", "KOSPI", "yahoo", "", "#1f8ce6"),
    ("KRW=X", "원/달러 환율", "yahoo", "원", "#0ea968"),
    ("bitcoin", "비트코인", "coingecko", "원", "#d97706"),
]

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "eyebrow": {"type": "string"},
        "read_minutes": {"type": "integer"},
        "body_html": {"type": "string"},
    },
    "required": ["title", "description", "eyebrow", "read_minutes", "body_html"],
}

PROMPT = """너는 한국 경제 매체의 기자다. 아래 지표 데이터와 최근 보도 목록만 근거로
지난 한 달 시장을 정리하는 분석 기사를 쓴다.

무엇을 쓸 것인가
A. 각 지표의 '특징' 항목이 이 기사의 핵심이다. 순변화율이 작아도 고저폭이 크면
   그 요동이 기사거리다. 한 달 순변화가 작다는 이유로 "보합", "숨고르기",
   "횡보"라고 쓰면 안 된다. 하루최대하락·하루최대상승·고저폭을 먼저 다룬다.
B. 최근 보도 목록에서 그 움직임과 시기가 겹치는 사건을 찾아 맥락으로 붙인다.
B-2. 거시지표(기준금리·물가·경상수지 등)가 주어지면 시세 움직임을 설명하는
   배경으로 쓴다. 다만 인과를 단정하지 않는다. 거시지표는 '표시' 문자열을 그대로
   쓰고 기준 시점을 밝힌다("7월 소비자물가 상승률 2.79%").
C. 현재값이 구간 어디에 있는지(현재값_구간내위치_퍼센트)로 지금 위치를 설명한다.

절대 규칙
1. 숫자는 주어진 데이터에 있는 것만 쓴다. 다른 수치를 절대 만들지 않는다.
2. 금액과 지수는 '최근값표시' 같은 **표시 문자열을 그대로** 쓴다.
   원시 실수(예: 90886406.15)를 본문에 쓰지 않는다. 퍼센트는 소수 두 자리까지다.
3. **투자자문으로 읽히면 안 된다.** 아래를 한 번이라도 쓰면 기사가 폐기된다.
   - 행동 권유: 매수, 매도, 사야, 팔아야, 비중 확대/축소, 손절, 익절, 진입 시점
   - 종목 추천: 추천, 유망, 최선호, 탑픽, 주목할 종목, 관심 종목
   - 가격 목표: 목표가, 목표주가, 적정주가
   - 결과 약속: 원금 보장, 수익 보장, 반드시 오른다, 무조건
   - 조급함 유도: 지금이 기회, 막차, 저점 매수
   - "투자 전략", "포트폴리오 구성", "대응 전략" 같은 말도 쓰지 않는다.
   우리는 무슨 일이 있었는지 적는다. 무엇을 하라고 적지 않는다.
3-1. 미래를 언급할 때는 **같은 문장 안에** 가정을 밝힌다.
   금지: 환율은 하방 압력을 유지할 것이다
   허용: 미 국채금리가 안정세를 이어가면 환율 하방 압력이 이어질 수 있다는 해석이 가능하다
4. 평서체로 쓴다. 존댓말을 쓰지 않는다.
5. 인용문이 없으므로 blockquote 를 쓰지 않는다.
6. 최근 보도 목록에 없던 사실을 지어내지 않는다. 특정 인물의 발언으로 단정하지 않는다.
7. 움직인 이유를 단정할 수 없으면 단정하지 않는다. "~와 시기가 겹친다",
   "~로 풀이된다" 처럼 관측 수준으로 쓴다.
8. 표는 본문 위에 코드가 이미 넣었다. 본문에서 표를 다시 만들지 않는다.

문장 규칙 (중요)
9. 세 절의 첫 문장을 서로 다른 구조로 시작한다. 같은 틀을 반복하지 않는다.
10. "N일간 관측된 ~는 최근값 ~을 기록하며" 같은 필드 낭독체를 쓰지 않는다.
    관측일수와 시작·종료일을 문장에 나열하지 않는다. 그건 표에 이미 있다.
11. 표에 있는 값을 그대로 되풀이하지 말고 그 값이 뜻하는 바를 쓴다.
12. 데이터의 **필드 이름을 문장에 쓰지 않는다.** "최근값표시", "기간최저표시",
    "현재값 구간내위치 퍼센트", "고저폭 퍼센트" 같은 말은 사람이 쓰는 한국어가 아니다.
    값만 쓰고 뜻은 자연스럽게 풀어 쓴다.
      나쁨: 최근값표시 6,852.58로 장을 마치며 현재값 구간내위치 퍼센트는 83.7%다
      좋음: 6,852.58로 마감해 한 달 등락 범위의 상단부에 다시 올라섰다
13. 날짜는 주어진 형식("7월 28일")을 그대로 쓴다. 2026-08-10 같은 표기를 쓰지 않는다.
14. 연속 상승·하락을 언급할 때는 **최장연속시작일~최장연속종료일 기간을 밝힌다.**
    그 구간이 최근인지 아닌지는 날짜로만 판단한다. 날짜를 확인하지 않고
    "최근 N일 연속"이라고 쓰지 않는다.

구성: 맨 앞에 h2 없는 도입 단락 하나, 이어서 h2 로 나눈 3개 절, 각 절에 2개 단락.
허용 태그: p, h2, h3, ul, ol, li, strong, em
title 은 40자 이내, description 은 한 문장, eyebrow 는 영문 2~3단어다.
"""


def recent_titles(cats=("경제", "암호화폐"), limit=8):
    """최근 기사 제목. 시장이 움직인 맥락을 LLM에게 주기 위한 것이다."""
    rows = []
    for path in glob.glob(os.path.join(ROOT, "articles", "*.html")):
        if path.endswith("-en.html"):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        cat = re.search(r'fs:category" content="([^"]+)', text)
        date = re.search(r'fs:date" content="([^"]+)', text)
        title = re.search(r"<title>(.*?)</title>", text, re.S)
        if cat and title and cat.group(1) in cats:
            name = html.unescape(title.group(1)).replace(article.TITLE_SUFFIX, "")
            rows.append((date.group(1) if date else "", name.strip(), cat.group(1)))
    rows.sort(reverse=True)
    return [{"날짜": d, "제목": t, "분야": c} for d, t, c in rows[:limit]]


def gather(indicators=None):
    """계획이 지정한 지표들의 시계열. 인자가 없으면 예전 기본값을 쓴다."""
    out = []
    for sym, name, src, unit, color in (indicators or DEFAULT_INDICATORS):
        stamps, values = (market.yahoo(sym) if src == "yahoo"
                          else market.coingecko(sym))
        last, pct = market.change(values)
        out.append({
            "이름": name, "단위": unit, "색": color, "값들": values,
            "최근값": round(last, 2), "한달변화율": round(pct, 2),
            "기간최저": round(min(values), 2), "기간최고": round(max(values), 2),
            "관측일수": len(values),
            "시작일": datetime.date.fromtimestamp(stamps[0]).isoformat(),
            "종료일": datetime.date.fromtimestamp(stamps[-1]).isoformat(),
            "기간": (f"{datetime.date.fromtimestamp(stamps[0]):%-m월 %-d일}"
                   if os.name != "nt" else
                   "{0.month}월 {0.day}일".format(
                       datetime.date.fromtimestamp(stamps[0]))
                   + " ~ " + "{0.month}월 {0.day}일".format(
                       datetime.date.fromtimestamp(stamps[-1]))),
            # LLM에는 아래 표시 문자열만 준다. 원시 실수를 주면 본문에 그대로 나온다.
            "최근값표시": label(last, unit),
            "기간최저표시": label(min(values), unit),
            "기간최고표시": label(max(values), unit),
            "특징": market.salients(stamps, values),
        })
    return out


def label(v, unit):
    """사람이 읽는 표기. LLM에는 이 문자열만 넘긴다.

    원시 실수를 넘겼더니 본문에 "90886406.15원"이 그대로 나왔다. 큰 원화는
    만·억 단위로 끊어야 읽힌다.
    """
    if unit == "":                      # 지수는 소수점 두 자리
        return f"{v:,.2f}"
    if unit == "원" and v >= 1e8:
        # "1.07억 원"은 한국어 표기가 아니다. 억과 만으로 끊는다.
        eok, man = int(v // 1e8), round((v % 1e8) / 1e4)
        if man >= 10000:                # 반올림으로 만이 넘치면 억으로 올린다
            eok, man = eok + 1, 0
        return f"{eok}억 원" if man == 0 else f"{eok}억 {man:,}만 원"
    if unit == "원" and v >= 1e4:
        man = round(v / 1e4)
        if man >= 10000:            # 9,999.95만이 "10,000만 원"으로 나오던 경계
            return f"{man // 10000}억 원"
        return f"{man:,}만 원"
    return f"{v:,.2f}{unit}"


def fmt(v, unit):
    """표 안에서 쓰는 짧은 표기."""
    return label(v, unit)


def related_video(cats=("경제",)):
    """기사 아래에 붙일 참고 영상 하나.

    **이 기사의 출처가 아니다.** 분석은 시장 데이터에서 나왔고, 영상은 같은 기간
    같은 주제를 다룬 다른 매체의 것이다. 그래서 '원본 영상'이 아니라 '참고 영상'으로
    표시하고, 요약본이 아니라는 문구를 함께 넣는다.

    이미 기사로 쓴 영상과 방송사가 아닌 채널은 거른다 — 참고로 걸어 두는 것이라
    본문보다 더 보수적으로 고른다.
    """
    import collect
    used = set()
    for path in (glob.glob(os.path.join(ROOT, "articles", "*.html"))
                 + glob.glob(os.path.join(DRAFTS, "*.html"))):
        try:
            with open(path, encoding="utf-8") as f:
                m = re.search(r'fs:(?:video|related_video)" content="([^"]+)', f.read())
        except Exception:
            continue
        if m:
            used.add(m.group(1))
    try:
        data = collect.collect(list(cats))
    except Exception:
        return None
    for v in data.get(cats[0], []):
        if v["id"] in used:
            continue
        if not collect.PREFERRED_CHANNEL.search(v["channel"]):
            continue
        # 남의 영상 제목이라도 우리가 골라 싣는 것이다. 본문에 못 쓰는 말이
        # 제목으로 들어오면 같은 페이지에서 기준이 어긋난다.
        # 실측: KBS "손절도 못하고 미치겠어요…" 가 1순위로 뽑혔다.
        if compliance.find_advice(v["title"]) or compliance.find_promise(v["title"]):
            continue
        return v
    return None


def video_block(video):
    """참고 영상 삽입. 없으면 통째로 빠진다."""
    if not video:
        return ""
    esc = lambda v: html.escape(str(v), quote=True)
    vid = esc(video["id"])
    return (
        '<figure class="related-video">\n'
        '  <figcaption class="related-video-head">참고 영상</figcaption>\n'
        '  <div class="video-embed">\n'
        f'    <iframe src="https://www.youtube.com/embed/{vid}" '
        f'title="{esc(video["title"])}" '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
        'gyroscope; picture-in-picture; web-share" '
        'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen '
        'loading="lazy"></iframe>\n'
        '  </div>\n'
        f'  <figcaption>{esc(video["channel"])} · '
        f'<a href="https://www.youtube.com/watch?v={vid}" target="_blank" '
        f'rel="noopener">{esc(video["title"])}</a><br />'
        '같은 기간 같은 주제를 다룬 다른 매체의 영상이다. '
        '이 기사는 위 영상의 요약이 아니며, 본문 수치는 공개 시장 데이터에서 가져왔다.'
        '</figcaption>\n</figure>')


def plan_meta(plan):
    """어떤 주제·형식으로 쓴 기사인지 남긴다.

    회전이 제대로 도는지 나중에 확인할 수 있어야 하고, 같은 주제가 며칠 만에
    돌아왔는지도 이 값으로 센다.
    """
    if not plan:
        return ""
    esc = lambda v: html.escape(str(v), quote=True)
    return (chr(10) + f'<meta name="fs:topic" content="{esc(plan["주제"])}" />'
            + chr(10) + f'<meta name="fs:format" content="{esc(plan["형식"])}" />')

def related_meta(video):
    """참고 영상 id 를 남긴다.

    fs:video 가 아니라 fs:related_video 다. fs:video 로 두면 publish 가 이 기사를
    영상 기사로 보고 카드 썸네일을 유튜브 이미지로 바꿔 버린다 — 이 기사의 카드는
    지표 차트여야 한다.
    """
    if not video:
        return ""
    v = html.escape(str(video["id"]), quote=True)
    return chr(10) + f'<meta name="fs:related_video" content="{v}" />'

def photo_meta(photo):
    """카드 배경 사진을 메타로 남긴다. 카드 조립은 publish/article 이 한다."""
    if not photo:
        return ""
    esc = lambda v: html.escape(str(v), quote=True)
    tags = [f'<meta name="fs:photo" content="{esc(photo["url"])}" />']
    if photo.get("by"):
        tags.append(f'<meta name="fs:photo_by" content="{esc(photo["by"])}" />')
    return chr(10).join(tags)

def card_thumb(rows, photo=None):
    """목록 카드에 쓸 썸네일을 기사 안에 심어 둔다.

    화면에는 보이지 않는다(hidden). publish.read_meta 가 이걸 꺼내 카드에 넣는다.
    카드에서 수치를 다시 계산하지 않으려고 기사 쪽에 함께 저장하는 방식이다.
    """
    if not rows:
        return ""
    r = rows[0]                     # 대표 지표(첫 항목)로 카드를 만든다
    svg = market.card_chart(r["값들"], r["이름"],
                           label(r["최근값"], r["단위"]), r["한달변화율"],
                           ground=not photo)
    if not svg:
        return ""
    return f'<div class="card-thumb" hidden>{svg}</div>'


def data_block(rows):
    """표 + 스파크라인. 코드가 그리므로 수치가 데이터와 어긋날 수 없다."""
    cells = []
    for r in rows:
        pct = r["한달변화율"]
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "―"
        klass = "up" if pct > 0 else "down" if pct < 0 else ""
        cells.append(
            "    <tr>\n"
            f'      <th scope="row">{r["이름"]}</th>\n'
            f'      <td class="num">{fmt(r["최근값"], r["단위"])}</td>\n'
            f'      <td class="num {klass}">{arrow} {abs(pct):.2f}%</td>\n'
            f'      <td class="spark">{market.sparkline(r["값들"], color=r["색"])}</td>\n'
            "    </tr>")
    span = f"{rows[0]['시작일']} ~ {rows[0]['종료일']}"
    return (
        '<figure class="data-block">\n'
        "  <table>\n"
        f"    <caption>주요 지표 · 최근 1개월 ({span})</caption>\n"
        '    <thead><tr><th scope="col">지표</th><th scope="col">최근</th>\n'
        '      <th scope="col">1개월 변화</th><th scope="col">추이</th></tr></thead>\n'
        "    <tbody>\n" + "\n".join(cells) + "\n    </tbody>\n"
        "  </table>\n"
        "  <figcaption>출처: Yahoo Finance(KOSPI·원/달러), CoinGecko(비트코인). "
        "수치는 발행 시점 종가 기준이며, 이 표와 그래프는 코드가 직접 생성한다."
        "</figcaption>\n</figure>")


def macro_block(rows):
    """거시지표 표. 값이 없으면 통째로 빠진다(ECOS 키가 없거나 응답 실패).

    시세 표가 "무엇이 얼마나 움직였나"라면 이 표는 "그때 배경이 어땠나"다.
    지표마다 공표 주기가 달라 기준 시점을 함께 보여 준다.
    """
    if not rows:
        return ""
    nl = chr(10)
    cells = []
    for r in rows:
        change = r.get("변화표시") or ""
        cells.append(
            "    <tr>" + nl
            + f'      <th scope="row">{r["이름"]}</th>' + nl
            + f'      <td class="num">{r["표시"]}</td>' + nl
            + f'      <td class="num">{change}</td>' + nl
            + f'      <td class="asof">{r["기준시점"]}</td>' + nl
            + "    </tr>")
    return (
        '<figure class="data-block macro-block">' + nl
        + "  <table>" + nl
        + "    <caption>거시지표</caption>" + nl
        + '    <thead><tr><th scope="col">지표</th><th scope="col">최근</th>' + nl
        + '      <th scope="col">직전 대비</th>'
          '<th scope="col">기준 시점</th></tr></thead>' + nl
        + "    <tbody>" + nl + nl.join(cells) + nl + "    </tbody>" + nl
        + "  </table>" + nl
        + "  <figcaption>출처: 한국은행 경제통계시스템(ECOS). "
          "지표마다 공표 주기가 달라 기준 시점이 다르다.</figcaption>" + nl
        + "</figure>")

BLOCK_CSS = """
.data-block{margin:38px 0;padding:0}
.data-block table{width:100%;border-collapse:collapse;font-size:.95rem}
.data-block caption{text-align:left;font-weight:700;padding-bottom:12px;color:var(--black)}
.data-block th,.data-block td{padding:12px 10px;border-bottom:1px solid var(--gray-200);text-align:left}
.data-block thead th{font-size:.8rem;letter-spacing:.04em;color:var(--gray-600);border-bottom-width:2px}
.data-block tbody th{font-weight:600;white-space:nowrap}
.data-block .num{font-variant-numeric:tabular-nums;white-space:nowrap}
.data-block .up{color:#e03040;font-weight:600}
.data-block .down{color:#1f8ce6;font-weight:600}
.data-block .spark{width:270px}
.data-block .spark svg{display:block;max-width:100%;height:auto}
.data-block figcaption{margin-top:14px;font-size:.82rem;line-height:1.6;color:var(--gray-600)}
@media (max-width:640px){.data-block .spark{display:none}}
.macro-block .asof{color:var(--gray-600);font-size:.88rem;white-space:nowrap}
"""


FIELD_WORDS = (
    "최근값표시", "기간최저표시", "기간최고표시", "한달변화율", "관측일수",
    # "고저폭"은 실제로 쓰이는 금융 용어라 목록에서 뺐다("고저폭 10.64%"는 자연스럽다).
    "현재값", "구간내위치", "최장연속", "하루최대상승", "하루최대하락",
    "최고가_먼저",
    # "특징"은 뺐다 — "5일 연속 상승을 기록한 점도 특징적이다" 는 자연스러운 한국어다.
    # "고저폭"과 같은 이유로, 필드 이름이면서 동시에 일상어인 낱말은 검사에서 제외한다.
)


def leaks(body_html):
    """본문에 데이터 필드 이름이 그대로 들어갔는지.

    "표시 문자열을 그대로 쓰라"고 지시했더니 LLM이 키 이름까지 문장에 옮겨 적어
    "최근값표시 6,852.58로 장을 마치며"가 나왔다. 프롬프트만으로는 못 막아서
    생성 후에 검사한다.
    """
    text = re.sub(r"<[^>]+>", " ", body_html)
    return [w for w in FIELD_WORDS if w in text]


DISCLAIMER = ("이 글은 공개된 시장 데이터를 정리한 정보 제공용 보도이며, "
              "투자 조언이나 권유가 아니다. Factory Magazine은 투자자문업 또는 "
              "유사투자자문업 등록 사업자가 아니고, 개별 종목·상품의 매매나 특정 "
              "시점의 매매를 권유하지 않는다. 수록된 수치는 발행 시점의 공개 데이터 "
              "기준이며 이후 달라질 수 있다. 투자 결정은 본인의 판단과 책임 하에 "
              "이루어져야 한다.")


def render_page(fields, rows, today, macro=(), photo=None, video=None,
                plan=None):
    body = article.tidy_body(article.validate_body(fields["body_html"]))
    esc = lambda v: html.escape(str(v), quote=True)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{esc(fields['title'])}{article.TITLE_SUFFIX}</title>
<meta name="description" content="{esc(fields['description'])}" />
<meta name="fs:category" content="경제" />
<meta name="fs:eyebrow" content="{esc(fields['eyebrow'])}" />
<meta name="fs:read" content="{esc(fields['read_minutes'])}" />
<meta name="fs:kind" content="analysis" />
{plan_meta(plan)}{photo_meta(photo)}{related_meta(video)}
<link rel="stylesheet" href="../css/style.css" />
<style>{BLOCK_CSS}</style>
</head>
<body>

{article._NAV}

<header class="article-hero">
  <div class="wrap">
    <a href="index.html" class="back-link">← 아티클 목록으로</a>
    <span class="section-eyebrow">{esc(fields['eyebrow'])}</span>
    <h1>{esc(fields['title'])}</h1>
    <div class="article-meta"><span class="byline-avatar">FS</span><span class="byline-name">{article.BYLINE}</span> · <span>{esc(fields['read_minutes'])}분 읽기</span> · <span>{today}</span></div>
  </div>
</header>

<article class="article-content">

{card_thumb(rows, photo)}

{data_block(rows)}

{macro_block(macro)}

{body}

{video_block(video)}

  <div class="disclaimer">
    이 글은 공개된 시장 데이터를 정리한 정보 제공용 보도이며, 투자 조언이나 권유가 아니다.
    Factory Magazine은 투자자문업 또는 유사투자자문업 등록 사업자가 아니고, 개별 종목·상품의
    매매나 특정 시점의 매매를 권유하지 않는다. 수록된 수치는 발행 시점의 공개 데이터
    기준이며 이후 달라질 수 있다. 투자 결정은 본인의 판단과 책임 하에 이루어져야 한다.
  </div>

</article>

{article._FOOTER}

<script src="../js/main.js"></script>
</body>
</html>
"""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)

    today_plan = agenda.plan()
    if today_plan is None:
        print("주말에는 발행하지 않습니다. (증시 휴장 — 금요일 종가가 그대로다)")
        return None
    print(f"오늘 계획: [{today_plan['형식이름']}] {today_plan['주제']} "
          f"— 지표 {len(today_plan['지표'])}종")

    print("지표 수집 중...")
    rows = gather(today_plan["지표"])
    for r in rows:
        print(f"  {r['이름']:8} {fmt(r['최근값'], r['단위']):>16}"
              f"  1개월 {r['한달변화율']:+.2f}%  ({r['관측일수']}일)")

    # 원시 실수와 그래프용 값은 넘기지 않는다. 표시 문자열과 특징만 넘긴다.
    drop = ("값들", "색", "최근값", "기간최저", "기간최고", "시작일", "종료일")
    facts = [{k: v for k, v in r.items() if k not in drop} for r in rows]
    context = recent_titles()
    print(f"맥락으로 넘길 최근 기사 {len(context)}건")

    # 카드 배경 사진. 없으면 차트만으로 카드가 그려진다.
    shot = pexels.photo(cfg, today_plan["사진검색어"])
    print(f"  카드 사진: {shot['by'] if shot else '없음(차트만)'}")

    clip = related_video()
    print(f"  참고 영상: {clip['channel'] + ' — ' + clip['title'][:34] if clip else '없음'}")

    # 거시지표. 실패해도 기사는 나간다 — 시세만으로도 기사는 성립한다.
    macro_rows = ecos.macro(cfg)
    if macro_rows:
        for m in macro_rows:
            print(f"  거시 {m['이름']:16} {m['표시']:>12}  ({m['기준시점']})")
    else:
        print("  거시지표 없음 — ECOS 키가 없거나 응답에 실패했습니다(기사는 진행)")

    payload = {
        "contents": [{"parts": [{"text": PROMPT
                                 + "\n\n오늘 기사의 형식: " + today_plan["형식이름"]
                                 + "\n" + today_plan["지시"]
                                 + "\n주제: " + today_plan["제목힌트"]
                                 + "\n\n지표 데이터:\n"
                                 + json.dumps(facts, ensure_ascii=False, indent=1)
                                 + "\n\n거시지표(한국은행 ECOS):\n"
                                 + json.dumps(macro_rows, ensure_ascii=False, indent=1)
                                 + "\n\n최근 보도 목록(맥락):\n"
                                 + json.dumps(context, ensure_ascii=False, indent=1)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "maxOutputTokens": cfg.get("max_output_tokens", 32768),
        },
    }
    print("분석 생성 중...")
    # gemini.request 가 candidates 파싱·잘림 검사까지 끝낸 값을 준다.
    fields, usage = gemini.request(cfg, payload, timeout=300)

    # 규제 게이트. 여기서 걸리면 초안을 파일로 쓰지 않는다.
    risky = compliance.blocking(compliance.check(
        fields["body_html"], fields["title"], DISCLAIMER))
    if risky:
        print(chr(10) + "  ⛔ 투자자문으로 읽힐 표현이 있어 초안을 만들지 않았습니다:")
        for _, kind, detail in risky:
            print(f"      [{kind}] {detail}")
        print("     프롬프트 3번 규칙 위반입니다. 다시 실행하세요.")
        return None
    print("  규제 검사 통과 (투자권유·수익보장·단정적 예측 0건)")

    bad = leaks(fields["body_html"])
    if bad:
        print(f"  ⛔ 필드 이름이 본문에 새어 나왔습니다: {', '.join(bad)}")
        print("     프롬프트 규칙 12번을 지키지 않은 결과입니다. 다시 생성하세요.")

    today = datetime.date.today().isoformat()
    os.makedirs(DRAFTS, exist_ok=True)
    # 주제마다 다른 파일명. 같은 이름이면 초안이 서로를 덮는다.
    stems = {"국내증시": "korea-stocks", "환율": "fx-market", "미국증시": "us-stocks",
             "원자재": "commodities", "아시아증시": "asia-stocks",
             "가상자산": "crypto-market", "주간리뷰": "weekly-market-review"}
    stem = stems.get(today_plan["주제"], "market-review")
    path = os.path.join(DRAFTS, f"{today}-{stem}.html")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(render_page(fields, rows, today, macro_rows, shot, clip, today_plan))
    print(f"\n완료  {path}")
    print(f"  {fields['title']}")
    print(f"  토큰 {usage}")
    return path


if __name__ == "__main__":
    main()
