# Factory Magazine

정치·경제·암호화폐·스포츠·세계·스타트업 6개 카테고리의 정적 콘텐츠 사이트.
유튜브 영상 링크 하나를 넣으면 그 내용을 요약한 기사를 만들어 사이트에 올린다.

```
py -3 tools\collect.py                    # 6개 카테고리 영상 후보 수집 (20초)
py -3 tools\draft.py <url1> <url2> ...    # 초안 생성 (최대 3개 동시)
py -3 tools\factcheck.py --write          # 네이버 뉴스로 고유명사·수치 대조
run_preview.bat                            # 브라우저로 검수
py -3 tools\publish.py --apply            # 발행
git push
```

6편을 만드는 데 **30~35분** 정도 걸린다. 대부분이 검수 시간이다.

---

## 처음 한 번만 (새로 합류하는 사람)

### 1. Python 설치

Python 3.10 이상. 설치 후 새 터미널에서 `py -3 --version`이 나오면 된다.
**설치할 패키지는 없다.** 표준 라이브러리만 쓴다.

### 2. 저장소 받기

```
git clone https://github.com/minjh8768-al/factorysignal-magazine.git
```

push 권한은 저장소 관리자에게 요청한다.

### 3. Gemini API 키 발급

https://aistudio.google.com/apikey 에서 본인 키를 만든다. 무료로 발급된다.

**키는 사람마다 따로 쓴다.** 무료 사용 한도가 키 단위라, 각자 키를 쓰면 서로의
한도를 잡아먹지 않는다.

### 4. 설정 파일 만들기

`tools\config.example.json`을 복사해 `tools\config.json`으로 저장하고 키를 채운다.

```json
{
  "gemini_api_key": "여기에 본인 키",
  "gemini_model": "gemini-2.5-flash",
  "media_resolution": "MEDIA_RESOLUTION_LOW",
  "max_output_tokens": 32768,

  "naver_client_id": "네이버 검색 API 키",
  "naver_client_secret": "네이버 검색 API 시크릿"
}
```

`config.json`은 `.gitignore`에 있어 저장소에 올라가지 않는다. **키를 공유하거나
커밋하지 말 것.**

### 5. 네이버 검색 API 키 (검수 자동화용)

`factcheck.py`가 기사의 인물·수치를 뉴스와 대조하는 데 쓴다. 없어도 나머지는 다 돌아가고,
그때는 검수를 손으로 하면 된다.

https://developers.naver.com → 애플리케이션 등록 → **사용 API에 "검색"** 선택 →
발급된 Client ID / Secret을 위 설정에 넣는다.

---

## 기사 한 편 만드는 절차

### 1) 영상 고르기

```
py -3 tools\collect.py            모든 카테고리 (20초)
py -3 tools\collect.py 스포츠 세계   지정한 카테고리만
```

카테고리별 후보를 번호가 붙은 표로 보여준다. 마음에 드는 것의 링크를 다음 단계에 넘긴다.

품질 필터가 걸려 있어서 아래는 후보에서 제외된다. `collect.py`의 `BAD_TITLE` /
`BAD_CHANNEL`이 **유일한 튜닝 지점**이고, 새로 걸러야 할 채널이 보이면 여기에 추가한다.

- 승부예측·베팅 채널 (매체 성격에 안 맞고 법적 위험)
- 낚시성 투자권유 제목 ("지금 사야", "폭등", "이렇게 하세요")
- 자동생성 내레이션 콘텐츠팜·예능 리캡 (화자가 없어 인용할 발언이 없다)
- 정치적 색이 강한 1인 논평 채널 (그 논조를 사이트가 그대로 뒤집어쓴다)
- 4분 미만 / 25분 초과, 오래된 영상

**요약할 만한 말이 있는 영상**을 고르는 것이 핵심이다. 하이라이트 영상처럼 내레이션이
없으면 요약할 내용이 없다. 10~20분이 적당하다(30분이면 약 18만 토큰).

### 2) 초안 생성

```
py -3 tools\draft.py https://youtu.be/xxxxxxxxxxx
py -3 tools\draft.py <url1> <url2> <url3>     여러 개를 동시에
```

`_drafts\YYYY-MM-DD-<slug>.html`이 만들어진다. 한 편에 1~2분,
여러 개를 넘기면 **최대 3개씩 동시에** 돌려서 6편이 3~4분에 끝난다.
3개로 제한한 것은 Gemini 무료 티어의 분당 요청 한도 때문이다.

카테고리·제목·소제목·읽기 시간은 자동으로 정해진다.

#### ⚠️ 하루 한도는 토큰이 아니라 요청 횟수다

`gemini-2.5-flash` 무료 티어는 **하루 20 요청**이다. 토큰은 넉넉하지만 이 횟수가 먼저
막힌다. 실측에서 6편을 한 번에 돌리다 4편이 여기에 걸렸다.

요청 1회로 세는 것: 초안 1편, 번역 1편, 실패 후 재시도 1회. 그래서 하루에 실제로
할 수 있는 양은 **초안 6편 + 영어판 6편 + 재시도 몇 번 = 약 15회**로 한도에 거의 닿는다.

**해결: 키를 여러 개 넣는다.** 발급이 무료이고 한도가 키마다 별도로 적용된다.

```json
"gemini_api_keys": ["키1", "키2", "키3"]
```

한 키가 하루 한도에 걸리면 자동으로 다음 키로 넘어간다(분당 한도는 기다려서 재시도).
키 3개면 하루 60 요청이다. 한도는 태평양시 자정(한국시간 오후 4~5시)에 초기화된다.

실패하는 경우:

| 메시지 | 뜻 |
| --- | --- |
| `닫히지 않은 태그가 있습니다` | 본문이 잘렸거나 깨졌다. 그냥 다시 실행하면 대개 된다 |
| `finishReason=MAX_TOKENS` | `config.json`의 `max_output_tokens`를 올린다 |
| `하루 요청 한도(무료 티어 20회)를 다 썼습니다` | 아래 참고. 키를 늘리거나 자정을 기다린다 |
| `카테고리가 6개 중 하나가 아닙니다` | 재실행 |

### 3) 자동 대조 — 무엇을 확인할지 좁힌다

```
py -3 tools\factcheck.py --write
```

초안에서 인물·날짜·수치를 뽑아 네이버 뉴스로 대조하고, 결과를 초안 `<head>` 위
주석으로 적어 둔다. `--write`를 빼면 화면에만 보여준다.

```
OK [인물] 정희용 사무총장 — 8282건
!! [인물] 곽상원 의원 — 근거 67건뿐 — 오기 의심
   · 노 전 대통령의 사위인 곽상언 의원은 ...        ← 근거 기사
?? [수치] 183표 — 근거 20건 — 아래 기사와 대조
   · 찬성 183표로 종결동의안이 통과됐다             ← 법안 표결이 아니라 종결동의안
```

| 태그 | 뜻 |
| --- | --- |
| `OK` | 뉴스에서 흔히 쓰이는 표기 (100건 이상) |
| `!!` | 근거가 얇다. 오기 의심 — 근거 기사를 읽고 판단 |
| `??` | 날짜·수치는 건수로 판정할 수 없다. 근거 기사와 직접 대조 |
| `ER` | 조회 실패 |

대조 소스는 셋이다. 각각 다른 곳에서 틀리므로 합쳐서 본다.

| 소스 | 쓰는 곳 | 키 |
| --- | --- | --- |
| 위키백과 (한/영) | 인물 표기·직함 | 불필요 |
| 네이버 뉴스 | 국내 사건·날짜·수치 | 필요 |
| Google News RSS | 해외 사안 (네이버에 근거가 없을 때) | 불필요 |

**판정은 힌트일 뿐 정답이 아니다.** 날짜는 특히 그렇다 — `8월 7일`은 뉴스에 88만 건이
나오지만 우리 기사와 같은 사건을 말하는지는 알 수 없다. 그래서 앞뒤 문맥 단어를 붙여
검색하고 근거 기사를 항상 보여준다. 읽고 판단하는 것은 사람이다.

이름이 아닌 말이 인물로 잡히기도 한다(`강경파와 대통령`). 무해하니 무시하면 된다.
반대로 걸러내려다 실제 인물을 놓치는 쪽이 더 나쁘다.

#### 이 도구가 못 잡는 오류

**"이름은 맞지만 지금 그 자리가 아닌" 오류.** 실측에서 현 연준 의장을 `제롬 파월`로 쓴
기사가 있었다(정답은 케빈 워시). 파월은 실존 인물이고 위키백과 문서도 있으니 표기 검증을
그대로 통과한다.

위키백과 첫 문단의 과거형 서술("역임")을 신호로 쓰려고 만들어 봤지만 **정반대로 작동해서
버렸다.** 한국어 위키백과의 파월 문서는 갱신이 늦어 아직 "의장이다"로 적혀 있고, 반대로
워시 문서에는 다른 과거 직책("이사회 위원을 역임")이 있어 오탐이 났다. 틀린 이름을
통과시키고 맞는 이름을 의심하는 셈이라 없는 게 낫다.

→ **직함이 현직인지는 사람이 확인해야 한다.** 특히 중앙은행 총재, 장관, 당직처럼 자주
바뀌는 자리가 위험하다.

### 4) 사람 검수 — 이 단계를 건너뛰지 말 것

```
run_preview.bat
```

브라우저가 열리면 `_drafts/` 안의 파일을 클릭해 읽는다. 발행 후와 똑같이 보인다.
`factcheck`가 적어 둔 `!!`·`??` 항목을 먼저 확인한다.

**반드시 원본 영상과 대조할 것:**

- **인명·직함** — 자주 틀린다. 실제로 `곽상언`을 `곽상원`, `인핸스`를 `이낸스`,
  현 연준 의장을 `파월`(→케빈 워시)로 썼다
- **날짜·숫자** — 같은 영상을 두 번 돌렸을 때 값이 달라진 적이 있다
- **`<blockquote>` 안의 직접 인용** — 음성인식 오류가 그대로 들어간다.
  남의 발언을 따옴표 안에서 틀리게 옮기는 것이라 가장 위험하다.
  화자가 실제로 한 말이 아니면 일반 `<p>`로 바꾸거나 지운다

`factcheck` 주석은 발행할 때 `publish.py`가 떼어내므로 사이트에는 남지 않는다.

고칠 것은 HTML을 직접 수정한다. 카테고리가 틀렸으면 `<head>`의 한 줄만 고치면 된다.

```html
<meta name="fs:category" content="정치" />
```

버릴 초안은 파일을 그냥 지우면 된다.

### 5) 발행

```
py -3 tools\publish.py            드라이런 — 무엇이 바뀔지만 보여준다
py -3 tools\publish.py --apply    실제 발행
git push
```

`--apply`가 하는 일:

1. `_drafts\*.html`을 `articles\`로 옮긴다
2. `articles\index.html`의 `<!-- CARDS:START/END -->` 사이를 다시 만든다
3. 발행일(`fs:date`)을 심는다 — 카드 정렬 기준

손으로 쓴 기존 카드(`bitcoin-the-perfect-ledger`)는 마커 밖에 있어 건드리지 않는다.

### 6) 영어판 만들기 (선택)

```
py -3 tools	ranslate.py                  영어판이 없는 기사 전부
py -3 tools	ranslate.py fomc             slug 일부로 지정
py -3 tools	ranslate.py --force fomc     이미 있어도 다시 만든다
```

`articles/<slug>-en.html`을 만들고 한국어판에 `English` 링크를 붙인다.
영상을 다시 읽히지 않고 이미 있는 한국어 본문만 번역하므로 **편당 약 2~3천 토큰**이다
(초안 생성은 11만 토큰). 6편이 65초, 총 1만 4천 토큰이었다.

영어판은 `fs:date`를 심지 않으므로 **목록에 카드가 생기지 않는다.** 한국어판 카드
하나만 노출되고, 기사 안에서 언어를 바꾼다. 한국어판을 내리면 영어판도 함께 지워진다.

**인용문은 한국어 원문을 그대로 두고 아래에 영어 번역을 붙인다.** 남의 발언이라
원문을 지우면 독자가 번역을 검증할 수 없다.

```html
<blockquote>정광재 동연정치연구소장은 "범죄자들은 …"라고 우려했다.</blockquote>
<p class="quote-tr">"I am truly worried that an era is coming where …"</p>
```

번역이 원문 구조를 바꾸면 파일을 만들지 않고 멈춘다. `<h2>`와 `<blockquote>` 개수가
원문과 같아야 한다. 실측에서 blockquote가 0개인 기사를 번역했더니 13개가 생겼다
(본문 안 인용부호를 승격시킴). 프롬프트에 개수를 숫자로 박아 넣어 줄였고,
개수 검사가 최종 방어선이다.

### 7) 내리기

```
py -3 tools\publish.py --list                  발행된 기사 목록
py -3 tools\publish.py --remove fomc           드라이런
py -3 tools\publish.py --remove fomc --apply   실제 삭제
git push
```

slug 일부만 적어도 찾는다.

---

## 여러 명이 같이 쓸 때

- `_drafts/`는 `.gitignore`라 검수 중인 초안은 서로 보이지 않고 충돌하지 않는다
- 두 사람이 같은 시각에 발행하면 `articles/index.html`에서 충돌할 수 있다.
  그때는 `git pull` 후 `py -3 tools\publish.py --apply`를 다시 실행하면 된다.
  인덱스는 `articles/`에 있는 파일을 보고 매번 새로 만들기 때문에 수동 병합이 필요 없다
- 발행 전에 `git pull`을 습관화하면 대부분 피할 수 있다

---

## 구조

```
articles/          발행된 기사 + index.html (목록 페이지)
_drafts/           검수 대기 초안 (gitignore)
css/  js/          공용 스타일·동작
tools/
  collect.py       카테고리별 영상 후보 수집 (+ 품질 필터)
  draft.py         유튜브 URL -> 초안 (여러 개 동시 처리)
  factcheck.py     인물·날짜·수치 대조 (위키백과·네이버·Google News)
  translate.py     한국어 기사 -> 영어판 (<slug>-en.html)
  publish.py       발행 · 발행 취소 · 목록
  article.py       템플릿 조립 · 검증 (순수 함수)
  gemini.py        Gemini 호출
  youtube.py       oEmbed로 채널·제목 조회
  naver.py         네이버 뉴스 검색
  wiki.py          위키백과 조회 (인물 표기·직함)
  gnews.py         Google News RSS (해외 사안)
  config.json      API 키 (gitignore)
run_preview.bat    로컬 미리보기 서버 (8093)
docs/superpowers/  설계 문서
```

테스트:

```
cd tools
py -3 -m unittest discover -p "test_*.py" -v
```

---

## 설계상 알아둘 것

**LLM이 만드는 것은 본문(`body_html`)뿐이다.** 상단 메뉴·푸터·영상 임베드·출처
표기·고지문은 코드가 고정으로 넣는다. 본문은 허용 태그 화이트리스트와 태그 짝
검사를 통과해야 하고, 하나라도 어긋나면 파일을 만들지 않고 멈춘다.

**출처 표기는 LLM에게 맡기지 않는다.** 채널명과 연도를 지어낸 적이 있어(2026년
영상을 "2022.07.31"로 표기) 유튜브 oEmbed에서 직접 가져온다.

**본문 문체는 '~다' 평서체다.** 뉴스 기사체이고, 프롬프트가 이렇게 지시한다.
영상 화자가 존댓말을 써도 본문은 평서체로 쓴다. 단 `<blockquote>` 안의 직접 인용은
화자가 말한 그대로 두므로 존댓말이 섞여도 정상이다. 고지문과 출처 문구는 코드가 넣는
정형 문장이라 존댓말을 유지한다.

**카테고리 색은 CSS에만 있다.** `css/style.css`가 `data-category` 값으로 카드 색과
태그 배지 색을 붙인다. 파이썬에 색을 복제하지 않는다.

**브랜드명은 `tools/article.py`의 `BRAND` 상수 한 곳에만 있다.** 로고 마크업
(`Factory<span> Magazine</span>`)만 `_NAV`·`_FOOTER` 템플릿에 직접 들어 있다.

자세한 내용은 `docs/superpowers/specs/2026-08-03-youtube-auto-article-design.md`.

---

## 배포

`main`(또는 `master`)에 push하면 Vercel이 배포한다. 1분 안에 반영된다.

라이브: https://factorysignal-magazine.vercel.app/articles/index.html

**배포가 안 되면 저장소가 private인지 먼저 확인한다.** 2026-08-03에 이 문제로 몇 시간을
썼다. push는 정상이었는데 Vercel이 새 배포를 만들지 않았고, 저장소를 public으로
바꾸자 바로 붙었다. 그다음 확인할 곳:

- Vercel 대시보드 → Deployments — 최신 커밋 빌드가 있는지, 실패했는지
- GitHub 저장소 → Settings → Webhooks — Vercel 훅의 Recent Deliveries (실패면 Redeliver)

배포를 못 기다릴 때는 `run_preview.bat`으로 로컬에서 확인한다.

### 알려진 문제: PC 이름이 한글이면 `vercel login`이 실패한다

```
Error: Cannot convert argument to a ByteString because the character at index 0
has a value of 52572 which is greater than 255
```

Vercel CLI가 로그인할 때 PC 이름을 HTTP 헤더에 넣는데 헤더는 ASCII만 받는다.
CLI 56·58 모두 같다. 토큰 인증은 이 흐름을 타지 않으므로 `.vercel-token` 파일에
토큰을 넣고 `deploy.bat`을 쓰면 우회된다.
