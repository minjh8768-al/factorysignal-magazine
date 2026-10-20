# -*- coding: utf-8 -*-
"""위키미디어 커먼즈에서 기사 '주인공'의 실제 사진을 찾는다 (2026-10-20).

왜 커먼즈인가
    리센느·축구대표팀·LG 트윈스처럼 특정 인물·팀의 사진은 Pexels 같은 스톡 사진에 없다.
    언론사·소속사 사진은 저작권이 있어 쓸 수 없다. 커먼즈에는 자유 이용이 허락된
    실제 사진(CC BY·CC BY-SA·CC0·퍼블릭 도메인·공공누리 1유형)이 많다.
    대신 CC BY 계열은 출처(촬영자·라이선스) 표기가 조건이라 카드에 함께 표시한다.

키가 필요 없다. 실패하면 None — 그때는 Pexels 장면 사진으로 물러선다.
"""
import json
import re
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "FactoryMagazine/1.0 (https://factorysignal-magazine.vercel.app)"

# 상업 이용·수정(잘라 보여 주기)이 허락된 라이선스만. NC(비상업)·ND(변경 금지)는 제외.
_OK = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? [\d.]+( [a-z]{2,3})?|kogl type 1)", re.I)
_BAD = re.compile(r"\b(nc|nd)\b", re.I)
# 기사 카드에 쓰면 안 되는 종류: 흉내 내는 사람·머그샷·로고·포스터·마스코트·만화.
_SKIP_TITLE = re.compile(r"impersonat|look-?alike|mug ?shot|logo|poster|emblem|mascot|caricature|"
                         r"cartoon|sticker|banner|wax|twitter|facebook|tweet|screenshot|blind|ibsa|"
                         r"paralympic|amputee", re.I)


def license_ok(name):
    name = (name or "").strip()
    return bool(_OK.match(name)) and not _BAD.search(name)


def _strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


MIN_PERSON_YEAR = 2023


def _year_from_title(title):
    m = re.search(r"\b(20[12]\d)\b", title) or re.search(r"(?<!\d)([12]\d)(?:0[1-9]|1[0-2])[0-3]\d(?!\d)", title)
    if not m:
        return 0
    y = m.group(1)
    return int(y) if len(y) == 4 else 2000 + int(y)


def candidates(query, limit=15, timeout=20):
    """조건(라이선스·크기·가로 비율)을 통과한 사진 목록 [{url, by, license, src}], 검색 순위순."""
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": "6", "gsrlimit": str(limit),
        "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": "960",
    }
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            pages = json.loads(r.read().decode("utf-8")).get("query", {}).get("pages", {})
    except Exception:
        return []
    out = []
    # 검색어의 핵심 낱말이 파일 이름에 실제로 있어야 한다 — 검색은 본문·분류까지 뒤져서
    # 'RESCENE'에 번호판 울타리 사진이 섞여 나왔다.
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z.\-]{3,}", query)]
    # 너무 작거나 세로로 긴 사진은 카드에서 얼굴이 잘려 건너뛴다.
    for p in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = _strip(meta.get("LicenseShortName", {}).get("value"))
        w, h = ii.get("width", 0), ii.get("height", 0)
        title = p.get("title", "")
        if not license_ok(lic) or w < 600 or (h and w / h < 0.9) or _SKIP_TITLE.search(title):
            continue
        if words and not any(word in title.lower() for word in words):
            continue
        if not all(m in title.lower() for m in MUST.get(query, ())) or title.lower().endswith(".gif"):
            continue
        # 촬영 연도: 메타데이터 → 없으면 파일 이름 속 연도 (예: '240611 대한민국 vs 중국' → 2024)
        year = re.search(r"(1[89]\d\d|20\d\d)", _strip(meta.get("DateTimeOriginal", {}).get("value")))
        year = int(year.group(1)) if year else _year_from_title(title)
        if year and year < 1990:      # 1950년대 흑백 대표팀 사진 같은 것
            continue
        # 사람·팀은 최근 사진만 (2010년 갤럭시S 행사 사진이 대표팀 기사에 붙었다). 연도를
        # 모르는 사진도 오래됐을 수 있으니 뺀다. 건물·장소는 연도를 따지지 않는다.
        if query not in PLACES and (not year or year < MIN_PERSON_YEAR):
            continue
        by = _strip(meta.get("Artist", {}).get("value"))[:60] or "Wikimedia Commons"
        # 다른 인물과 함께 찍힌 사진('A and B', 'with')은 엉뚱한 기사에서 오해를 살 수 있어 뒤로 미룬다.
        solo = not re.search(r"(?i)[ _](and|with|meets|&)[ _]", title)
        out.append({"url": ii.get("thumburl") or ii.get("url"), "by": by,
                    "license": lic, "src": ii.get("descriptionurl", ""), "solo": solo})
    solos = [c for c in out if c["solo"]]
    return (solos or out)[:POOL_MAX.get(query, 99)]


def search(query, pick=0):
    """{url, by, license, src} 또는 None. pick: 같은 주인공 기사끼리 사진을 바꿔 쓰는 순번."""
    found = candidates(query)
    return found[pick % len(found)] if found else None


# 주인공은 있는데 쓸 수 있는 실사진이 없을 때: 원본 유튜브 영상의 썸네일을 출처와 함께 쓴다.
# (요약·임베드하는 바로 그 영상의 미리보기. 채널이 요청하면 내린다.) 2026-10-20 사용자 결정.
VIDEO = "@video"


def video_thumb(video_id, channel):
    """원본 영상 썸네일을 카드 사진 형식으로. maxres가 없는 영상은 카드에서 mqdefault로 바꾼다."""
    return {"url": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            "by": channel or "YouTube", "license": "원본 영상", "src": f"https://www.youtube.com/watch?v={video_id}"}


# 예전 기사용: 제목 속 이름 → 커먼즈 검색어. 위에서부터 첫 일치. (새 기사는 Gemini photo_subject)
# 2026-10-20 사진 대조 검수 후 정리: 엉뚱한 사진이 나온 이름(한동훈·윤석열 → 다른 사람,
# KIA → 실제 호랑이, 코스피 → 자동차, KBO·LoL·이강인·안세영·야구 대표팀·아시안게임·아마존)은 뺐다.
# 사람을 잘못 붙이는 것은 사진이 없는 것보다 훨씬 나쁘다 — 새 이름은 결과를 눈으로 확인하고 넣는다.
SUBJECTS = (
    ("리센느", "RESCENE"), ("손흥민", "Son Heung-min"),
    ("LoL", VIDEO),                  # 'LoL 대표팀'이 축구 대표팀으로 가지 않게 여기서 멈춘다
    ("야구 대표팀", VIDEO),          # 커먼즈 결과가 대표팀 사진이 아니었다
    # 축구 대표팀: 커먼즈의 최근 사진이 상대팀(요르단) 단체 사진이었고 한국 대표팀 최근 사진은 없었다.
    # 옛날 사진·남의 팀 사진보다 장면 사진이 낫다 → 실사진을 쓰지 않는다.
    ("축구대표팀", VIDEO), ("축구 대표팀", VIDEO), ("대표팀", VIDEO),
    # 실사진이 엉뚱하게 나왔던 인물: 원본 영상 썸네일로
    ("한동훈", VIDEO), ("윤석열", VIDEO), ("이강인", VIDEO), ("안세영", VIDEO), ("롤드컵", VIDEO),
    ("잠실", "Jamsil Baseball Stadium"),
    ("트럼프", "Donald Trump at the 2026 FIFA World Cup final"), ("백악관", "White House"),
    ("이재명", "Lee Jae-myung"), ("이 대통령", "Lee Jae-myung"),
    ("국회", "National Assembly Proceeding Hall"), ("최태원", "Chey Tae-won"),
    ("연준", "Marriner S. Eccles Federal Reserve Board Building"),
    ("FOMC", "Marriner S. Eccles Federal Reserve Board Building"),
    ("한국은행", "Bank of Korea"), ("가자", "Gaza Strip"), ("레바논", "Beirut"),
    ("요르단", "Petra Jordan"), ("엔비디아", "Nvidia"), ("삼성", "Samsung Electronics"),
    ("비바테크", VIDEO),               # 커먼즈 사진이 다른 나라(튀니지) 대표단 사진이었다
)


# 제목에 이름이 없을 때 꼬리표로 정하는 주인공. 국내 야구 기사는 잠실야구장 실사진.
EYEBROW_SUBJECTS = {"야구": "Jamsil Baseball Stadium"}

# 검색어별로 파일 이름에 반드시 있어야 하는 낱말 (잠실 '야경'·'철교' 사진 등을 거르려고).
MUST = {"Jamsil Baseball Stadium": ("baseball",)}

# 검색어별로 쓸 후보 수 상한. 트럼프: 백악관 1월 사진은 붉은 조명의 연출 사진이라 쓰지 않고,
# 정장 차림의 중립적인 사진(2026 월드컵 결승) 1장만 쓴다. 2번째 후보는 BTS 공연 사진.
POOL_MAX = {"Donald Trump at the 2026 FIFA World Cup final": 1}

# 제목만으로는 주인공이 드러나지 않는 기사를 직접 지정 (slug → 검색어).
OVERRIDES = {
}


def subject_for(title, eyebrow="", slug=""):
    """기사 주인공 검색어. 빈 검색어("")에 걸리면 거기서 멈추고 실사진을 쓰지 않는다."""
    if slug in OVERRIDES:
        return OVERRIDES[slug]
    for word, q in SUBJECTS:
        if word in (title or ""):
            return q
    return EYEBROW_SUBJECTS.get(eyebrow, "")


# 건물·장소 — 오래된 사진이어도 괜찮은 검색어 (사람·팀은 MIN_PERSON_YEAR 이후 사진만).
PLACES = {
    "White House", "National Assembly Proceeding Hall", "Marriner S. Eccles Federal Reserve Board Building",
    "Bank of Korea", "Gaza Strip", "Beirut", "Petra Jordan", "Nvidia", "Samsung Electronics",
    "VivaTech", "Jamsil Baseball Stadium",
}
