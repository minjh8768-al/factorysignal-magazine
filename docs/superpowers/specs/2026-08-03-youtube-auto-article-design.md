# 유튜브 영상 → 기사 자동 생성 파이프라인 (설계)

작성일: 2026-08-03
대상 저장소: `factorysignal-magazine`

## 목적

유튜브 영상 링크 하나를 붙여넣으면, 그 영상 내용을 요약한 기사를
`articles/bitcoin-the-perfect-ledger.html`과 동일한 형식으로 생성한다.
카테고리(정치·경제·암호화폐·스포츠·세계·스타트업) 분류, 제목, 소제목, 인용문,
읽기 시간, 카드 썸네일 문구까지 모두 자동으로 뽑는다.

사람은 발행 전 검수만 한다.

## 성공 기준

1. `py -3 tools\draft.py <유튜브URL>` 한 줄로 `_drafts/`에 검수 가능한 완성형 HTML이 생성된다.
2. 그 HTML을 브라우저에서 열면 발행 후와 동일하게 보인다.
3. `py -3 tools\publish.py --apply` 후 `articles/index.html`의 카드 그리드·사이드바 필터·footer 목록이
   손대지 않아도 맞는다.
4. Gemini가 무엇을 반환하든 사이트 마크업이 깨지지 않는다.

## 검증된 사실 (2026-08-03 실측)

Gemini API는 유튜브 URL을 `fileData.fileUri`로 직접 받아 영상+오디오를 읽는다.
자막 추출 라이브러리·스크래핑·yt-dlp가 전부 불필요하다.

`gemini-2.5-flash`로 `https://www.youtube.com/watch?v=9N5yh59WMoI`(bitcoin 기사 원본 영상) 테스트:

| 설정 | 총 프롬프트 토큰 | 영상 | 오디오 | 정확도 |
| --- | --- | --- | --- | --- |
| 기본 | 508,630 | 453,412 | 55,145 | 정확 |
| `mediaResolution: MEDIA_RESOLUTION_LOW` | 177,635 | 122,404 | 55,145 | 가장 정확 |
| `videoMetadata.fps: 0.2` | 145,966 | 90,735 | 55,145 | 세부 정보 일부 뭉갬 |

**`MEDIA_RESOLUTION_LOW`를 채택한다.** 토큰을 65% 줄이면서 정확도가 오히려 더 높았다
(진행자 이름, 총 발행량 2,100만 개, 타임스탬프까지 포착).
오디오 55,145 토큰이 바닥값이며 이것이 실제 내용이다. 영상 트랙은 뉴스 요약에 거의 기여하지 않는다.

`gemini-2.0-flash`는 이 API 키에서 quota 0이다(HTTP 429). **`gemini-2.5-flash` 단일 모델에 의존한다.**

## 구조

```
factorysignal-magazine/
├─ articles/          발행된 기사
├─ _drafts/           검수 대기 초안 (.gitignore)
├─ css/  js/
├─ docs/superpowers/  설계·계획 문서
└─ tools/
   ├─ draft.py        유튜브 URL → 초안 HTML
   ├─ publish.py      초안 → articles/ + 인덱스 갱신 + 커밋
   ├─ article.py      템플릿 조립 · 태그 검증 · 카드 생성 (순수 함수)
   ├─ gemini.py       Gemini 호출 + 재시도 (travel/gemini.py 패턴)
   ├─ config.json     API 키 (.gitignore)
   ├─ config.example.json
   └─ test_article.py 네트워크 없는 단위테스트
```

표준 라이브러리만 사용한다(`travel`·`sky`와 동일 패턴). 드라이런이 기본이고 `--apply`로 실행한다.

### 모듈 경계

- **`gemini.py`** — 프롬프트를 받아 텍스트를 반환한다. HTML도 기사도 모른다.
  429/503 재시도를 담당한다.
- **`article.py`** — 순수 함수만 담는다. Gemini가 준 필드 딕셔너리를 받아 완성 HTML 문자열을 반환하고,
  카드 HTML을 만들고, 카드 구간을 교체한다. 네트워크·파일 IO가 없어 테스트가 쉽다.
- **`draft.py`** — 두 모듈을 이어 붙이고 `_drafts/`에 쓴다.
- **`publish.py`** — 파일 이동, 인덱스 갱신, git 커밋.

`article.py`를 IO에서 분리하는 이유는 이 파이프라인에서 깨질 여지가 가장 큰 부분(LLM 출력 →
마크업 조립)을 네트워크 없이 반복 검증하기 위해서다.

## 데이터 흐름

```
유튜브 URL
  → gemini.py: fileData(fileUri) + mediaResolution LOW + JSON 스키마 프롬프트
  → JSON 필드 검증 (카테고리 6개 소속 · 허용 태그 화이트리스트)
  → article.py: 고정 템플릿에 body_html 삽입
  → _drafts/YYYY-MM-DD-<slug>.html
       ↓  사람이 브라우저로 열어 검수 · 수정 · 폐기
  → publish.py: articles/ 이동 → index.html 카드 구간 재생성 → footer 갱신 → git commit
  → git push → Vercel 배포
```

### Gemini 반환 필드

| 필드 | 설명 | 예 |
| --- | --- | --- |
| `title` | 기사 제목 | `비트코인은 "가장 완벽한 장부"다 — 오태민 교수에게 듣는 2026년 크립토 전망` |
| `description` | `<meta name="description">` | `지식인사이드 인터뷰 요약: …` |
| `slug` | 파일명용 영문 슬러그 | `bitcoin-the-perfect-ledger` |
| `category` | 6개 중 하나 (한글) | `암호화폐` |
| `eyebrow` | 히어로 영문 라벨 겸 카드 태그 | `Market Watch` |
| `read_minutes` | 읽기 시간 (정수) | `8` |
| `source_title` | 원본 영상 표기용 채널·제목 | `지식인사이드 · 지식인초대석 EP.90` |
| `body_html` | 본문 | `<p>…</p><h2>…</h2>…` |

프롬프트는 "영상에서 화자가 실제로 말한 내용만 근거로 삼고, 확인되지 않은 사실을 채우지 말라"를
명시한다. 인용문은 화자의 발언을 그대로 옮긴 것만 `<blockquote>`에 넣는다.

## LLM 출력 격리 (가장 중요한 설계 결정)

Gemini는 **`body_html`만** 생성한다. 다음은 전부 코드가 고정 삽입한다.

- `<nav>` 블록, `<footer>` 블록
- `video-embed` iframe (URL에서 추출한 video id로 조립)
- `source-note` 단락 — 코드가 요소를 조립하고 링크 주소는 video id에서, 링크 텍스트만
  `source_title`에서 가져온다. "요약·정리한 것입니다" 문구는 고정이다.
- `disclaimer` 블록
- `article-hero` (back-link, eyebrow, h1, byline)

`body_html`은 허용 태그 화이트리스트로 검증한다: `p` `h2` `h3` `blockquote` `ul` `ol` `li`
`strong` `em` `a`. 그 밖의 태그가 나오면 **거부하고 멈춘다**(조용히 제거하지 않는다 —
본문이 잘려나간 채 발행되는 것보다 실패가 낫다).

`category`가 6개 밖의 값이면 거부하고 멈춘다. 잘못된 카테고리로 조용히 발행되는 것이 최악이다.

## 카테고리 처리

유효한 값은 여섯 개뿐이다: `정치` `경제` `암호화폐` `스포츠` `세계` `스타트업`.

**파이썬에 색상 표를 넣지 않는다.** 카테고리 색은 이미 `css/style.css`에 있고
`data-category` 속성만으로 동작한다.

- `style.css:677-682` — `.article-card[data-category="…"] .article-thumb` 그라디언트
- `style.css:828-833` — `.article-card[data-category="…"] .article-tag` 배지 색

따라서 `publish.py`가 할 일은 `data-category`에 올바른 한글 값을 넣는 것뿐이고, CSS가 나머지를
처리한다. 사이드바 필터(`js/main.js`)도 같은 속성으로 동작한다. 색상 값을 파이썬에 복제하면
CSS와 어긋날 수 있으므로 복제하지 않는다.

카테고리에서 파생하는 것은 `disclaimer` 문구 하나뿐이다.
암호화폐·경제는 투자 위험 고지를 포함하고, 정치·세계·스포츠·스타트업은
"출연자 개인 견해이며 Factory Magazine이 검증·보증하지 않는다"만 넣는다.

### 카드 썸네일은 영상 썸네일을 쓴다

이 파이프라인이 만드는 기사는 전부 영상 기반이므로 카드는 그라디언트가 아니라
`bitcoin-the-perfect-ledger` 카드와 동일한 형태를 쓴다.

```html
<div class="article-thumb article-thumb--video"
     style="background-image:url('https://img.youtube.com/vi/<VIDEO_ID>/hqdefault.jpg');"><span>▶</span></div>
```

`.article-thumb--video`(`style.css:684-696`)가 그라디언트를 덮고 재생 아이콘을 얹는다.
카드에 넣을 텍스트 라벨이 필요 없다.

## 초안 ↔ 발행 사이의 메타데이터 전달

초안 HTML `<head>`에 메타 태그로 심는다. 사이드카 JSON을 쓰지 않는다.

```html
<meta name="fs:category" content="암호화폐" />
<meta name="fs:eyebrow" content="Market Watch" />
<meta name="fs:read" content="8" />
<meta name="fs:video" content="9N5yh59WMoI" />
```

카드에 필요한 나머지 두 값은 이미 초안 HTML에 있으므로 중복해서 심지 않는다.

- 카드 제목 → `<title>`에서 `article.TITLE_SUFFIX` 접미사를 떼어 얻는다
- 카드 발췌문 → `<meta name="description">`

`publish.py`가 이 값들을 읽어 카드를 만든다. 검수자가 카테고리나 제목을 고치고 싶으면 지금 읽고
있는 그 파일을 수정하면 되고, 파일과 메타데이터가 어긋날 수 없다.
`fs:` 태그는 발행 후에도 남긴다(무해하며 기사의 분류를 문서화한다).

## 인덱스 자동 갱신

`articles/index.html`은 현재 전부 수작업 HTML이라 자동 삽입 지점이 없다. 마커 주석을 넣는다.

```html
<div class="article-grid">
  <!-- CARDS:START -->
  ...
  <!-- CARDS:END -->
</div>
```

`publish.py`는 이 구간을 통째로 재생성한다(최신 기사가 앞). footer의 아티클 목록도
같은 방식(`<!-- FOOTER-LIST:START/END -->`)으로 갱신한다.

정적 HTML을 유지하므로 SEO·SNS 미리보기에 영향이 없다.
`articles.json` + JS 렌더 방식은 카드가 자바스크립트로 그려져 검색엔진에 불리해 채택하지 않는다.

### 카드 개수와 그리드

`CLAUDE.md`는 `.article-grid` 4열 유지를 명시한다. 기사가 늘어나면 4열 그리드에 여러 행이
생기며, 이는 Outstanding 스타일 밀집 배치와 부합하므로 CSS 변경 없이 그대로 둔다.
`publish.py`는 카드 개수를 제한하지 않는다.

## 경로가 맞아떨어지는 지점

`_drafts/`는 `articles/`와 같은 깊이(저장소 루트 바로 아래)다. 따라서 초안 HTML의
`../css/style.css`가 그대로 유효하고, 브라우저에서 초안을 열면 발행 후와 동일하게 보이며
발행 시 경로를 고칠 필요가 없다.

초안 미리보기에서 nav·footer의 상대 링크(`index.html` 등)는 `_drafts/` 안을 가리켜 동작하지 않는다.
본문 검수에는 지장이 없어 그대로 둔다.

## 오류 처리

| 상황 | 처리 |
| --- | --- |
| 유효하지 않은 유튜브 URL | video id 추출 실패 시 즉시 중단 |
| Gemini 429 (한도 소진) | 서버 권고 대기(최대 35초) 후 3회 재시도, 실패 시 한글 안내 후 중단 |
| Gemini 503 | 동일 재시도 |
| JSON 파싱 실패 | 원본 응답을 `_drafts/<slug>.raw.txt`로 남기고 중단 |
| 허용 안 된 태그 | 어떤 태그인지 출력하고 중단 (제거하지 않음) |
| 카테고리 6개 밖 | 반환값을 출력하고 중단 |
| slug 중복 | 기존 `articles/` · `_drafts/`와 대조해 `-2` 접미사 부여 |
| 마커 주석 없음 | `publish.py`가 안내 후 중단 (인덱스를 추측해 고치지 않음) |

`_drafts/`의 파일을 삭제하면 그 초안은 폐기된다. 별도 명령이 필요 없다.

## 테스트

`tools/test_article.py` — `unittest`, 네트워크 없음:

- 허용 태그만 있는 `body_html`은 통과하고, `<script>` 포함 시 예외가 발생한다
- 6개 카테고리는 통과하고, `연예` 같은 값은 예외가 발생한다
- 생성된 카드의 `data-category`가 입력 카테고리와 정확히 일치한다 (CSS가 색을 붙이는 유일한 근거)
- 생성된 카드가 `article-thumb--video`와 해당 video id의 `img.youtube.com` 썸네일을 쓴다
- 암호화폐 기사에는 투자 위험 문구가, 정치 기사에는 없는 것이 확인된다
- 카드 구간 재생성이 `<!-- CARDS:START/END -->` 밖의 HTML을 건드리지 않는다
- 마커가 없는 인덱스를 넣으면 예외가 발생한다
- 같은 slug가 이미 있으면 `-2`가 붙는다
- 유튜브 URL 여러 형태(`youtu.be/x`, `watch?v=x`, `watch?v=x&t=10`, `youtube.com/shorts/x`)에서
  같은 video id를 얻는다
- 초안 HTML에서 `fs:` 메타와 `<title>`·`description`을 다시 읽어 카드를 만드는 왕복이 손실 없이 된다

실행: `cd tools && py -3 -m unittest discover -p "test_*.py" -v`

## 범위에서 제외한 것

- **네이버 검색 API** — 소재 발굴·사실 보강 용도로 나중에 붙일 수 있다. v1은 사람이 링크를 고른다.
- **자동 탐색(`collect.py`)** — 링크 붙여넣기가 번거로워지면 추가한다.
- **크론 자동 발행** — 검수 없는 발행은 LLM이 지어낸 사실·오보를 그대로 공개하므로 하지 않는다.
- **발행일 표시, OG 태그, sitemap, 검색 기능** — 이 저장소에 필요한 개선이지만 이 파이프라인과
  독립이므로 별도로 다룬다.

## 설정

`tools/config.json`(`.gitignore`):

```json
{
  "gemini_api_key": "...",
  "gemini_model": "gemini-2.5-flash",
  "media_resolution": "MEDIA_RESOLUTION_LOW"
}
```

키는 `G:\내 드라이브\claude\travel\config.json`의 `gemini_api_key`를 재사용한다.
`media_resolution`을 설정으로 노출하는 이유는 영상 길이·품질에 따라 조정할 여지를 남기기 위해서다
(짧은 영상은 기본 해상도가 더 정확할 수 있다).

## 브랜드명은 한 곳에만 둔다

`article.py`의 `BRAND` / `TITLE_SUFFIX` / `BYLINE` 상수가 유일한 정의다.

2026-08-03 작업 중 저장소가 `factorysignal` -> `Factory Magazine`으로 리브랜딩됐다.
그때 `render()`가 붙이는 제목 접미사와 `publish.py`가 떼는 접미사가 각각 하드코딩돼 있어서,
떼는 쪽이 옛 문자열을 찾지 못해 인덱스 카드 제목에 `" — Factory Magazine"`이 그대로
남았다. 붙이는 쪽과 떼는 쪽이 같은 상수를 쓰게 하고, `render()` 출력을 `publish.read_meta()`로
다시 파싱하는 왕복 테스트로 재발을 막는다.

`nav-logo`는 `Factory<span> Magazine</span>`처럼 브랜드명 중간에 태그가 들어가므로 상수로
조립하지 않고 `_NAV` / `_FOOTER` 템플릿에 그대로 둔다. 다음 리브랜딩 때 손봐야 할 곳은
`BRAND` 상수와 이 두 템플릿뿐이다.

## 운영상 한도

30분 영상 1편이 약 18만 토큰을 소비하고, `gemini-2.5-flash` 무료 티어 하나에 의존한다.
하루에 몇 편까지 가능한지는 실사용으로 확인해야 한다. 짧은 영상이 유리하다.
한도가 문제가 되면 `media_resolution`을 낮추거나 유료 키로 전환한다.
