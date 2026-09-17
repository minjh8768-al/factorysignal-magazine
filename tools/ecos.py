# -*- coding: utf-8 -*-
"""한국은행 ECOS 거시지표. 분석 기사의 '왜 움직였나'를 뒷받침할 근거를 가져온다.

시세(KOSPI·환율·코인)는 market.py 가, 정책·물가 같은 거시지표는 여기가 맡는다.
시세만 있으면 "무엇이 얼마나 움직였다"까지만 쓸 수 있고, 그 이유를 데이터로
말하려면 기준금리·물가·경상수지가 필요하다.

키는 config.json 의 ecos_api_key. 무료이고 ecos.bok.or.kr 에서 즉시 발급된다.
키가 없으면 macro() 가 빈 목록을 돌려준다 — 거시지표가 없다고 기사가 실패하면 안 된다.

통계표·항목 코드는 추측하지 않고 StatisticTableList / StatisticItemList 로 실제
확인한 값만 쓴다(아래 MACRO 의 주석이 확인된 이름이다).
"""
import datetime
import json
import urllib.request

BASE = ("https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/{rows}"
        "/{stat}/{cycle}/{start}/{end}/{item}")

# (표시이름, 통계표, 주기, 항목코드, 단위표기, 계산방식)
#   level = 최근값 그대로        (기준금리, 국고채 금리)
#   yoy   = 전년 같은 달 대비 %  (소비자물가지수 → 물가상승률)
#   sum12 = 최근 12개월 합계     (경상수지 → 연간 누계 감각)
MACRO = [
    # 1.3.1. 한국은행 기준금리 및 여수신금리 / 한국은행 기준금리
    ("한국은행 기준금리", "722Y001", "D", "0101000", "%", "level"),
    # 1.3.2.1. 시장금리(일별) / 국고채(5년)
    ("국고채 5년 금리", "817Y002", "D", "010200001", "%", "level"),
    # 4.2.1. 소비자물가지수 / 총지수
    ("소비자물가 상승률", "901Y009", "M", "0", "%", "yoy"),
    # 2.5.1.2. 경상수지(계절조정) / 경상수지
    ("경상수지", "301Y017", "M", "SA000", "백만달러", "level"),
]


def _get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def series(key, stat, cycle, item, start, end, rows=400):
    """([(기간, 값)], 단위). 값이 빈 칸인 행은 버린다.

    단위는 ECOS 가 알려주는 UNIT_NAME 을 쓴다. 코드에 적어 두면 통계 개편으로
    단위가 바뀌었을 때 조용히 틀린 숫자를 싣게 된다.
    """
    url = BASE.format(key=key, rows=rows, stat=stat, cycle=cycle,
                      start=start, end=end, item=item)
    data = _get(url)
    if "StatisticSearch" not in data:            # {"RESULT": {...}} = 오류
        raise RuntimeError(data.get("RESULT", {}).get("MESSAGE", "ECOS 오류"))
    out, unit = [], ""
    for row in data["StatisticSearch"]["row"]:
        v = (row.get("DATA_VALUE") or "").strip()
        if v:
            out.append((row["TIME"], float(v)))
            unit = row.get("UNIT_NAME") or unit
    return out, unit


def human(value, unit):
    """기사에 그대로 쓸 표기.

    '44,427.6백만달러'는 한국 기사에서 쓰지 않는 단위다. 억 달러로 끊는다.
    """
    if unit in ("연%", "%"):
        return f"{value:,.2f}%"
    if unit == "백만달러":
        return f"{value / 100:,.0f}억 달러"
    if unit == "십억원":
        return f"{value / 10:,.0f}억 원"
    return f"{value:,.2f}{unit}"


def span(cycle, today=None):
    """주기에 맞는 조회 구간. 월간은 전년 대비를 내야 해서 15개월을 본다."""
    d = today or datetime.date.today()
    if cycle == "D":
        return (d - datetime.timedelta(days=60)).strftime("%Y%m%d"), d.strftime("%Y%m%d")
    y, m = (d.year - 2, d.month) if d.month <= 3 else (d.year - 1, d.month - 3)
    return f"{y}{m:02d}", f"{d.year}{d.month:02d}"


def yoy(rows):
    """전년 같은 기간 대비 변화율. 월간 지수를 상승률로 바꿀 때 쓴다.

    지수(2020=100)를 그대로 기사에 쓰면 아무 뜻이 없다. 사람이 아는 숫자는 상승률이다.
    """
    if len(rows) < 13:
        return None
    (t_now, v_now), (_, v_before) = rows[-1], rows[-13]
    return t_now, round((v_now - v_before) / v_before * 100, 2)


def macro(cfg, today=None):
    """기사에 넣을 거시지표. 실패한 항목은 조용히 빠진다.

    ECOS 가 죽어도 기사는 나가야 한다. 시세 데이터만으로도 기사는 성립한다.
    """
    key = (cfg or {}).get("ecos_api_key", "")
    if not key:
        return []
    out = []
    for name, stat, cycle, item, _hint, how in MACRO:
        try:
            start, end = span(cycle, today)
            rows, unit = series(key, stat, cycle, item, start, end)
            if not rows:
                continue
            if how == "yoy":
                got = yoy(rows)
                if not got:
                    continue
                when, value = got
                unit = "%"          # 지수를 상승률로 바꿨으므로 단위도 바뀐다
                prev = None
            else:
                when, value = rows[-1]
                prev = rows[-2][1] if len(rows) > 1 else None
            out.append({
                "이름": name, "값": round(value, 2), "단위": unit,
                "표시": human(value, unit),
                "기준시점": pretty_time(when),
                "직전표시": human(prev, unit) if prev is not None else None,
                # 변화량도 표시 단위로 낸다. 원시 차이(+6306.50)를 그대로 두면
                # 본문의 "444억 달러"와 단위가 어긋난다.
                "변화표시": (("+" if value >= prev else "-") + human(abs(value - prev), unit)
                          if prev is not None else None),
            })
        except Exception:
            continue          # 항목 하나가 실패해도 나머지는 살린다
    return out


def pretty_time(t):
    """ECOS 의 '20260825' / '202607' 을 사람이 읽는 형태로."""
    if len(t) == 8:
        return f"{int(t[4:6])}월 {int(t[6:8])}일"
    if len(t) == 6:
        return f"{t[:4]}년 {int(t[4:6])}월"
    return t
