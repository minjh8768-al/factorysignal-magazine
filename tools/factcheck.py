# -*- coding: utf-8 -*-
"""초안의 고유명사·직함·수치를 네이버 뉴스로 대조한다.

    py -3 factcheck.py                       _drafts의 모든 초안
    py -3 factcheck.py _drafts\2026-08-03-x.html
    py -3 factcheck.py --write                판정을 초안 HTML 주석으로 넣는다

이 도구는 정답을 주지 않는다. "무엇을 확인해야 하는지"를 좁혀 주고 근거 기사를
보여주는 것이 목적이다. 판단은 사람이 한다.

판정 방식이 종류마다 다르다:
  인물   이름+직함으로 검색해 근거 건수를 본다. 흔한 표기는 수백~수천 건,
         오기는 수십 건에 그친다. (실측: 곽상언 459건 / 곽상원 67건)
  날짜·수치  건수로는 판정할 수 없다. "8월 7일"은 88만 건이 나오지만 그 기사가
         우리 기사와 같은 사건을 말하는지는 알 수 없다. 그래서 앞뒤 문맥 단어를
         붙여 검색하고, 판정 없이 근거 기사를 항상 보여준다.
"""
import glob
import html
import json
import os
import re
import sys

import gnews
import naver
import wiki

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DRAFTS = os.path.join(ROOT, "_drafts")

MARK_START = "<!-- FACTCHECK:START"
MARK_END = "FACTCHECK:END -->"

# 근거 건수 임계값. 곽상원(67건)이 !!로, 곽상언(459건)이 OK로 갈리는 지점.
PLENTY = 100

# 직함. "시장"·"선수"는 "주식 시장"·"축구 선수"처럼 일반명사로 걸려 제외했다.
TITLES = ("교수", "의원", "소장", "평론가", "총장", "사무총장", "장관", "부총리",
          "총리", "대통령", "위원장", "의장", "청장", "처장", "지사", "앵커", "기자",
          "회장", "부회장", "사장", "감독", "코치", "차관", "실장", "본부장",
          "대변인", "연구원", "원장", "이사", "단장")

# 이름 자리에 들어오지만 사람 이름이 아닌 말들. 실제 실행에서 걸러야 했던 것들이다.
NOT_A_NAME = frozenset((
    "정치", "경제", "주식", "부동산", "민주당", "국민", "강경파", "유일하게",
    "이번", "지금", "현재", "관련", "우리", "모든", "다른", "같은", "국내",
    "해외", "대한", "이런", "그런", "어떤", "당시", "최근", "일부", "전체",
    "그리고", "하지만", "그러나", "따라서", "여당", "야당", "정부", "국회",
    "미국", "중국", "일본", "한국", "시장", "기업", "회사", "대표",
))

# 소속 접두어는 2자 이상만 허용한다. 0자를 허용하면 "유일하게 반대표"에서 "반"+"대표"로
# 쪼개져 사람 이름이 아닌 것을 잡는다. 뒤에 오는 조사(의원'만이')는 그냥 둔다.
# 소속에 공백을 허용한다. 없으면 "파월 연준 의장"이 잡히지 않는다.
RE_PERSON = re.compile(
    r"([가-힣]{2,4})\s+((?:[가-힣]{2,10}\s?)?(?:%s))" % "|".join(TITLES))
RE_DATE = re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일|\d{1,2}월\s*\d{1,2}일|\d{4}년")
RE_NUMBER = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:%|퍼센트|표|명|억 원|억원|조 원|조원|포인트|석)")

# 문맥 검색어를 만들 때 빼는 조사·기능어
RE_WORD = re.compile(r"[가-힣A-Za-z][가-힣A-Za-z0-9]*")
FILLER = frozenset(("그리고", "하지만", "그러나", "이번", "지금", "현재", "또한",
                    "이에", "따라", "위해", "대해", "대한", "관련", "있다", "했다",
                    "된다", "이다", "라고", "라며", "면서", "때문"))


def body_text(path):
    """기사 본문만 평문으로. nav·footer·고지문은 제외한다."""
    with open(path, encoding="utf-8") as f:
        s = f.read()
    marker = "것입니다.</p>"
    start = s.find(marker)
    end = s.find('<div class="disclaimer"')
    if start == -1 or end == -1:
        return "", s
    body = s[start + len(marker):end]
    return html.unescape(re.sub(r"<[^>]+>", " ", body)), s


def context_query(text, start, end, written, window=45):
    """숫자·날짜 앞뒤에서 뜻이 있는 단어를 골라 검색어를 만든다.

    "8월 17일 민주당 전당대회"처럼 주변 단어를 붙이지 않으면, 날짜만으로는 우리 기사와
    같은 사건을 말하는 기사인지 알 수 없다.
    """
    around = text[max(0, start - window):start] + " " + text[end:end + window]
    words = [w for w in RE_WORD.findall(around)
             if len(w) >= 2 and w not in FILLER and not w.isdigit()]
    return " ".join(words[:3] + [written]) if words else written


def extract(text):
    """확인할 항목을 뽑는다. [(종류, 표기, 검색어)]

    인물은 검색어 자리에 (이름, 직함) 튜플을 넣는다. 위키백과로 따로 확인하기 때문이다.
    """
    items, seen = [], set()

    def add(kind, written, query):
        key = (kind, written)
        if written and key not in seen:
            seen.add(key)
            items.append((kind, written, query))

    for m in RE_PERSON.finditer(text):
        name, title = m.group(1), m.group(2)
        if name in NOT_A_NAME:
            continue
        add("인물", f"{name} {title}", (name, title))
    for m in RE_DATE.finditer(text):
        w = m.group(0).strip()
        add("날짜", w, context_query(text, m.start(), m.end(), w))
    for m in RE_NUMBER.finditer(text):
        w = m.group(0).strip()
        add("수치", w, context_query(text, m.start(), m.end(), w))
    return items


def verdict(kind, total):
    """뉴스 건수 기반 판정. 날짜·수치는 건수로 판정하지 않는다."""
    if total is None:
        return "ER", "조회 실패"
    if kind != "인물":
        return "??", f"근거 {total}건 — 아래 기사와 대조"
    if total == 0:
        return "??", "뉴스에서 못 찾음 — 직접 확인"
    if total < PLENTY:
        return "!!", f"근거 {total}건뿐 — 오기 의심"
    return "OK", f"{total}건"


def check_person(name, title):
    """위키백과 + 뉴스 건수를 합쳐 인물 표기를 본다. (태그, 설명, 근거줄들)

    두 소스를 합치는 이유는 각각 다른 곳에서 틀리기 때문이다. 실측:
      곽상언  위키 있음               -> 실존
      곽상원  위키 없음 + 뉴스 67건    -> 오기 (잡아야 할 것)
      정광재  위키 없음 + 뉴스 789건   -> 실존. 위키만 보면 오탐이 난다
      정희용  위키 있음, 첫 문단에 '사무총장' 없음 -> 실존. 위키 첫 문단이 낡았을 뿐
      이석현  위키가 동명이인 안내 페이지 -> 위키로는 판정 불가
    그래서 '위키에 없고 뉴스도 얇을 때'만 오기로 의심한다. 직함 불일치는 참고 메모로만
    남기고 확인 대상으로 세지 않는다.
    """
    extract_ko, err = wiki.lookup(name, "ko")
    total, payload = naver.search(cfg_holder["cfg"], f'"{name}" {title}', display=2)
    news = f"뉴스 {total}건" if total is not None else "뉴스 조회 실패"

    if err:
        # 위키가 막히면 뉴스 건수만으로 판단한다
        tag, note = verdict("인물", total)
        return tag, f"{note} (위키백과 조회 실패)", \
            [f"· {t[:74]}" for t, _ in (payload or [])[:2]] if total else []

    if extract_ko and not wiki.is_disambiguation(extract_ko):
        snippet = extract_ko[:150]
        if wiki.title_matches(extract_ko, title):
            return "OK", f"위키백과 문서·직함 일치 · {news}", [snippet]
        return "OK", f"위키백과 문서 있음 · {news} · 직함은 확인 권장", \
            [snippet, f"기사가 쓴 직함: {title} (위키 첫 문단에 없음 — 최근 직책일 수 있음)"]

    # 위키에 없거나 동명이인 페이지 -> 뉴스 건수로 판단
    where = "동명이인 페이지" if extract_ko else "위키백과 문서 없음"
    if total is None:
        return "ER", f"{where} · 뉴스 조회 실패", []
    if total >= PLENTY:
        return "OK", f"{where}이지만 {news} — 실존으로 봄", []
    hints = [t for t in wiki.search(name, "ko") if t != name][:3]
    lines = [f"· {t[:74]}" for t, _ in (payload or [])[:2]]
    if hints:
        lines.append(f"비슷한 표제어: {', '.join(hints)}")
    return "!!", f"{where} + {news}뿐 — 오기 의심", lines


def check_context(kind, written, query):
    """날짜·수치를 뉴스로 대조한다. 국내 근거가 없으면 Google News로 넘어간다."""
    total, payload = naver.search(cfg_holder["cfg"], query, display=2)
    if total:
        tag, note = verdict(kind, total)
        return tag, note, [f"검색: {query}"] + \
            [f"· {t[:74]}\n  {d[:74]}" for t, d in payload[:2]]

    # 국내 보도가 없으면 해외 사안일 수 있다
    g_total, g_payload = gnews.search(query, lang="ko", limit=2)
    if g_total is None:
        first = payload if isinstance(payload, str) else "국내 근거 없음"
        return "??", f"근거 없음 ({first})", [f"검색: {query}"]
    if not g_total:
        return "??", "네이버·Google News 모두 근거 없음 — 직접 확인", [f"검색: {query}"]
    return "??", f"Google News {g_total}건 — 아래 기사와 대조", \
        [f"검색: {query} (Google News)"] + \
        [f"· {t[:74]}  ({s})" for t, s in g_payload[:2]]


cfg_holder = {"cfg": {}}


def check_file(cfg, path, write):
    text, raw = body_text(path)
    name = os.path.basename(path)
    if not text:
        print(f"[{name}] 본문을 찾지 못했습니다 (형식이 다른 파일?)")
        return
    items = extract(text)
    print(f"\n{'=' * 82}\n[{name}]  확인 항목 {len(items)}개")

    cfg_holder["cfg"] = cfg
    lines, need_check = [], 0
    for kind, written, query in items:
        if kind == "인물":
            tag, note, evidence = check_person(*query)
        else:
            tag, note, evidence = check_context(kind, written, query)

        print(f"  {tag:2} [{kind}] {written}  — {note}")
        lines.append(f"{tag} [{kind}] {written} — {note}")
        if tag != "OK":
            need_check += 1
        for line in evidence if tag != "OK" else []:
            for sub in line.split("\n"):
                print(f"       {sub}")

    print(f"\n  확인 필요: {need_check}건 / 전체 {len(items)}건")

    if write:
        block = (MARK_START + "\n     네이버 뉴스 대조. OK=흔한 표기, !!=오기 의심, "
                 "??=사람이 대조 필요, ER=조회 실패.\n"
                 + "\n".join("     " + l for l in lines) + "\n     " + MARK_END)
        raw = re.sub(re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\n?", "",
                     raw, flags=re.S)
        doctype = "<!DOCTYPE html>\n"
        if raw.startswith(doctype):
            raw = doctype + block + "\n" + raw[len(doctype):]
        else:
            raw = block + "\n" + raw
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(raw)
        print(f"  → 판정을 {name} 주석으로 기록 (DOCTYPE 바로 뒤)")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    write = "--write" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]

    cfg_path = os.path.join(HERE, "config.json")
    if not os.path.exists(cfg_path):
        sys.exit("config.json이 없습니다. config.example.json을 복사해 키를 채우세요.")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("naver_client_id"):
        sys.exit("config.json에 naver_client_id / naver_client_secret이 필요합니다.\n"
                 "https://developers.naver.com 에서 '검색' API로 앱을 등록하세요.")

    paths = args or sorted(glob.glob(os.path.join(DRAFTS, "*.html")))
    if not paths:
        sys.exit("검사할 초안이 없습니다.")
    for path in paths:
        check_file(cfg, path, write)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
