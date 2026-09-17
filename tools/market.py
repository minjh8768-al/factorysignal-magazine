# -*- coding: utf-8 -*-
"""시장 데이터. API 키가 필요 없는 곳만 쓴다.

기사 본문의 숫자를 LLM이 말하게 두지 않기 위한 모듈이다. 수치는 여기서 계산해
프롬프트에 넣고, 표와 차트는 코드가 그린다. LLM은 문장만 쓴다.
"""
import json
import urllib.parse
import urllib.request

YAHOO = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         "{symbol}?range={rng}&interval=1d")
COINGECKO = ("https://api.coingecko.com/api/v3/coins/{cid}/market_chart"
             "?vs_currency=krw&days={days}&interval=daily")
UA = {"User-Agent": "Mozilla/5.0"}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def yahoo(symbol, rng="1mo"):
    """종가 시계열. 휴장일(None)은 버린다."""
    d = _get(YAHOO.format(symbol=urllib.parse.quote(symbol), rng=rng))
    res = d["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    stamps = res["timestamp"]
    pairs = [(t, c) for t, c in zip(stamps, closes) if c is not None]
    return [t for t, _ in pairs], [c for _, c in pairs]


def coingecko(cid="bitcoin", days=30):
    d = _get(COINGECKO.format(cid=cid, days=days))
    pts = d["prices"]
    return [int(t / 1000) for t, _ in pts], [v for _, v in pts]


def change(values):
    """(최근값, 기간 변화율%). 값이 2개 미만이면 변화율은 None."""
    if not values:
        return None, None
    if len(values) < 2:
        return values[-1], None
    return values[-1], (values[-1] - values[0]) / values[0] * 100


def sparkline(values, w=260, h=56, color="#1f8ce6"):
    """의존성 없는 인라인 SVG. 값이 2개 미만이면 빈 문자열."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = (w - 4) / (len(values) - 1)
    pts = " ".join(
        f"{2 + i * step:.1f},{h - 4 - (v - lo) / span * (h - 8):.1f}"
        for i, v in enumerate(values))
    last_x, last_y = pts.split(" ")[-1].split(",")
    return (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
        f'aria-label="최근 추이" preserveAspectRatio="none">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="3" fill="{color}"/></svg>')


def card_chart(values, label, value_text, pct, w=300, h=180, ground=True):
    """목록 카드용 썸네일 차트.

    본문 표의 스파크라인을 카드에 그대로 쓰면 단색 배경에 실선 하나뿐이라
    자리표시자처럼 보인다. 카드는 사진 썸네일들과 나란히 놓이므로 그 자체로
    읽을 것이 있어야 한다 — 지표명·현재값·변화율을 함께 그린다.

    선 색은 등락 방향을 따른다(상승 빨강·하락 파랑). 국내 시장 관행이라
    색만 보고도 방향을 안다.
    """
    if len(values) < 2:
        return ""
    up = pct >= 0
    line = "#ff4d5e" if up else "#3d9bff"
    fill = "rgba(255,77,94,.20)" if up else "rgba(61,155,255,.20)"
    arrow = "▲" if up else "▼"

    top, bottom = 96, h - 14           # 차트가 쓰는 세로 구간
    lo, hi = min(values), max(values)
    span_v = (hi - lo) or 1
    step = (w - 28) / (len(values) - 1)
    pts = [(14 + i * step, bottom - (v - lo) / span_v * (bottom - top))
           for i, v in enumerate(values)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"14,{bottom} {poly} {pts[-1][0]:.1f},{bottom}"
    grid = "".join(
        f'<line x1="0" y1="{y}" x2="{w}" y2="{y}" stroke="rgba(255,255,255,.07)"/>'
        for y in (top + 14, (top + bottom) // 2, bottom))

    # 사진을 배경으로 쓸 때는 바탕과 격자를 그리지 않는다. 사진 위에 겹치면
    # 지저분해지고, 가독성용 어두운 막은 CSS 가 씌운다.
    if ground:
        base = (
            f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="#12161c"/>'
            f'<stop offset="1" stop-color="#1d2530"/></linearGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="url(#bg)"/>{grid}')
        shadow = ""
    else:
        # 사진 위에서는 글자와 선이 배경에 묻힌다. 그림자를 깔아 떼어 놓는다.
        base = ('<defs><filter id="sh" x="-20%" y="-20%" width="140%" height="140%">'
                '<feDropShadow dx="0" dy="1" stdDeviation="2.5" '
                'flood-color="#000" flood-opacity=".85"/></filter></defs>')
        shadow = ' filter="url(#sh)"'

    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" height="100%" role="img" '
        f'aria-label="{label} {value_text} {pct:+.2f}%" '
        f'preserveAspectRatio="none">'
        f'{base}'
        f'<polygon points="{area}" fill="{fill}"/>'
        f'<polyline{shadow} points="{poly}" fill="none" stroke="{line}" stroke-width="2.4" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.4" fill="{line}"/>'
        f'<text{shadow} x="14" y="30" fill="rgba(255,255,255,.75)" '
        f'font-family="system-ui,-apple-system,sans-serif" font-size="12" '
        f'font-weight="700" letter-spacing="1.4">{label}</text>'
        f'<text{shadow} x="14" y="66" fill="#ffffff" '
        f'font-family="system-ui,-apple-system,sans-serif" font-size="27" '
        f'font-weight="800" letter-spacing="-0.5">{value_text}</text>'
        f'<text{shadow} x="{w - 14}" y="66" fill="{line}" text-anchor="end" '
        f'font-family="system-ui,-apple-system,sans-serif" font-size="15" '
        f'font-weight="700">{arrow} {abs(pct):.2f}%</text>'
        f'</svg>')


def salients(stamps, values):
    """시계열에서 '기사거리'를 코드가 찾아낸다.

    최근값·최고·최저만 넘겼더니 LLM이 순변화율(-0.7%)만 보고 "숨고르기"라고 썼다.
    실제로는 한 달 안에 5,593에서 7,096까지 27% 폭으로 요동친 구간이었다.
    무엇이 특이한지는 사람이 판단해야 하는데, 판단 재료는 코드가 줄 수 있다.
    """
    import datetime
    # 본문에 그대로 인용되므로 한국식으로 낸다. ISO 를 주면 "2026-08-10~2026-08-14"가
    # 문장 안에 섞여 "2026년 7월 28일"과 형식이 어긋난다.
    def day(t):
        d = datetime.date.fromtimestamp(t)
        return f"{d.month}월 {d.day}일"
    lo, hi = min(values), max(values)
    i_lo, i_hi = values.index(lo), values.index(hi)

    steps = [(values[i] - values[i - 1]) / values[i - 1] * 100
             for i in range(1, len(values))]
    i_up = max(range(len(steps)), key=lambda i: steps[i]) if steps else None
    i_dn = min(range(len(steps)), key=lambda i: steps[i]) if steps else None

    # 같은 방향으로 며칠 연속 갔는지. 추세인지 톱니인지 구분하는 재료다.
    best_run, run, sign = 0, 0, 0
    best_dir, best_end = 0, 0
    for i, s in enumerate(steps):
        cur = 1 if s > 0 else -1 if s < 0 else 0
        run = run + 1 if cur == sign and cur != 0 else 1
        sign = cur
        if run > best_run:
            best_run, best_dir, best_end = run, cur, i

    return {
        "고저폭_퍼센트": round((hi - lo) / lo * 100, 2),
        "최고일": day(stamps[i_hi]), "최저일": day(stamps[i_lo]),
        "최고가_먼저": i_hi < i_lo,
        "하루최대상승_퍼센트": round(steps[i_up], 2) if steps else None,
        "하루최대상승일": day(stamps[i_up + 1]) if steps else None,
        "하루최대하락_퍼센트": round(steps[i_dn], 2) if steps else None,
        "하루최대하락일": day(stamps[i_dn + 1]) if steps else None,
        "최장연속": best_run,
        "최장연속방향": "상승" if best_dir > 0 else "하락" if best_dir < 0 else "보합",
        # 연속 구간이 '언제'였는지 없으면 LLM이 "최근 6일 연속"처럼 시점을 지어낸다.
        "최장연속시작일": day(stamps[best_end + 1 - best_run + 1]) if best_run else None,
        "최장연속종료일": day(stamps[best_end + 1]) if best_run else None,
        "현재값_구간내위치_퍼센트": round((values[-1] - lo) / ((hi - lo) or 1) * 100, 1),
    }
