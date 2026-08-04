# Factory Magazine

정치·경제·암호화폐·스포츠·세계·스타트업 6개 카테고리의 정적 콘텐츠 사이트.
유튜브 영상 링크 하나를 넣으면 그 내용을 요약한 기사를 만들어 사이트에 올린다.

```
py -3 tools\draft.py https://youtu.be/xxxxxxxxxxx   # 초안 생성
run_preview.bat                                      # 브라우저로 검수
py -3 tools\publish.py --apply                       # 발행
git push
```

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
  "max_output_tokens": 32768
}
```

`config.json`은 `.gitignore`에 있어 저장소에 올라가지 않는다. **키를 공유하거나
커밋하지 말 것.**

---

## 기사 한 편 만드는 절차

### 1) 영상 고르기

요약할 만한 **말이 있는 영상**을 고른다. 하이라이트 영상처럼 내레이션이 없으면
요약할 내용이 없다.

피해야 할 것:

- 승부예측·베팅 채널 (매체 성격에 안 맞고 법적 위험)
- 정치적 색이 강한 1인 논평 채널 (그 논조를 사이트가 그대로 뒤집어쓴다)
- 자동생성 내레이션 콘텐츠팜 (화자가 없어 인용할 발언이 없다)

10~20분 영상이 적당하다. 길수록 토큰을 많이 쓴다(30분 = 약 18만 토큰).

### 2) 초안 생성

```
py -3 tools\draft.py https://www.youtube.com/watch?v=xxxxxxxxxxx
```

`_drafts\YYYY-MM-DD-<slug>.html`이 만들어진다. 1~2분 걸린다.
카테고리·제목·소제목·읽기 시간은 자동으로 정해진다.

실패하는 경우:

| 메시지 | 뜻 |
| --- | --- |
| `닫히지 않은 태그가 있습니다` | 본문이 잘렸거나 깨졌다. 그냥 다시 실행하면 대개 된다 |
| `finishReason=MAX_TOKENS` | `config.json`의 `max_output_tokens`를 올린다 |
| `Gemini 무료 한도를 다 썼습니다` | 다음 날 다시 하거나 다른 키를 쓴다 |
| `카테고리가 6개 중 하나가 아닙니다` | 재실행 |

### 3) 검수 — 이 단계를 건너뛰지 말 것

```
run_preview.bat
```

브라우저가 열리면 `_drafts/` 안의 파일을 클릭해 읽는다. 발행 후와 똑같이 보인다.

**반드시 원본 영상과 대조할 것:**

- **인명·직함** — 자주 틀린다. 실제로 `곽상언`을 `곽상원`, `인핸스`를 `이낸스`로 썼다
- **날짜·숫자** — 같은 영상을 두 번 돌렸을 때 값이 달라진 적이 있다
- **`<blockquote>` 안의 직접 인용** — 음성인식 오류가 그대로 들어간다.
  남의 발언을 따옴표 안에서 틀리게 옮기는 것이라 가장 위험하다.
  화자가 실제로 한 말이 아니면 일반 `<p>`로 바꾸거나 지운다

고칠 것은 HTML을 직접 수정한다. 카테고리가 틀렸으면 `<head>`의 한 줄만 고치면 된다.

```html
<meta name="fs:category" content="정치" />
```

버릴 초안은 파일을 그냥 지우면 된다.

### 4) 발행

```
py -3 tools\publish.py            드라이런 — 무엇이 바뀔지만 보여준다
py -3 tools\publish.py --apply    실제 발행
git push
```

`--apply`가 하는 일:

1. `_drafts\*.html`을 `articles\`로 옮긴다
2. `articles\index.html`의 `<!-- CARDS:START/END -->` 사이를 다시 만든다
3. 발행일(`fs:date`)을 심는다 — 카드 정렬 기준

손으로 쓴 기존 카드 4개는 마커 밖에 있어 건드리지 않는다.

### 5) 내리기

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
  draft.py         유튜브 URL -> 초안
  publish.py       발행 · 발행 취소 · 목록
  article.py       템플릿 조립 · 검증 (순수 함수)
  gemini.py        Gemini 호출
  youtube.py       oEmbed로 채널·제목 조회
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

**카테고리 색은 CSS에만 있다.** `css/style.css`가 `data-category` 값으로 카드 색과
태그 배지 색을 붙인다. 파이썬에 색을 복제하지 않는다.

**브랜드명은 `tools/article.py`의 `BRAND` 상수 한 곳에만 있다.** 로고 마크업
(`Factory<span> Magazine</span>`)만 `_NAV`·`_FOOTER` 템플릿에 직접 들어 있다.

자세한 내용은 `docs/superpowers/specs/2026-08-03-youtube-auto-article-design.md`.

---

## 배포

`main`에 push하면 Vercel이 배포한다.

**2026-08-03 현재 이 경로가 동작하지 않는다.** push는 되지만 Vercel이 새 배포를
만들지 않아 라이브 사이트가 갱신되지 않는다. Vercel 프로젝트 소유자만 확인할 수
있는 영역이다. 확인할 곳:

- Vercel 대시보드 → Deployments — 최신 커밋 빌드가 있는지, 실패했는지
- GitHub 저장소 → Settings → Webhooks — Vercel 훅의 Recent Deliveries

그때까지는 `run_preview.bat`으로 로컬에서 결과물을 확인한다.

### 알려진 문제: PC 이름이 한글이면 `vercel login`이 실패한다

```
Error: Cannot convert argument to a ByteString because the character at index 0
has a value of 52572 which is greater than 255
```

Vercel CLI가 로그인할 때 PC 이름을 HTTP 헤더에 넣는데 헤더는 ASCII만 받는다.
CLI 56·58 모두 같다. 토큰 인증은 이 흐름을 타지 않으므로 `.vercel-token` 파일에
토큰을 넣고 `deploy.bat`을 쓰면 우회된다.
