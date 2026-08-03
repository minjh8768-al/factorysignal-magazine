# factory Magazine — site context

Static HTML/CSS content site for **factory Magazine**, the content/media brand under
factorysignal Holdings. This is its OWN standalone repo/Vercel project (`factorysignal-magazine`),
deliberately split out from the `predict-analytics` repo (which holds the actual app) so that
magazine writers/editors can get repo access without ever seeing the app's code. Deploys
automatically on push to `main`.

## Naming — read this before touching any brand text

"predictanalytics-news" is only ever a domain/repo name. The actual prediction-market app
brands itself **"factorysignal"** in its own UI (see `polymarket-news/index.html`'s header
logo). To avoid the two properties both being called bare "factorysignal", this site is now
**"factory Magazine"** everywhere a visible label appears (nav logo, page titles, footer
brand text, byline, copyright line). The founder explicitly dropped "signal" from this site's
own name to keep it distinct from the app — don't reintroduce "factorysignal" or
"factorysignal Magazine" as this site's display name. The footer's "링크" column still
legitimately says "factorysignal" once — that entry links to and correctly names the *other*
property (the app), leave it alone.

**Public URL stays `predictanalytics-news.vercel.app/blog/`** even though the code now lives
here — the main app's `vercel.json` has a rewrite that proxies `/blog/*` to this project's own
Vercel deployment URL. If you need the raw deployment URL (e.g. to update that rewrite), check
this project's Vercel dashboard; don't assume it matches the repo name exactly.

Separate again from factorysignal-holdings, the parent-company corporate site — also its own
repo, also linked from here, but a different visual identity (see below).

Referred to as **"Magazine"** everywhere in nav/copy — deliberately renamed from "블로그"/"Blog".
Keep using "Magazine" (English word, unchanged) if this site ever gets multi-language support
like factorysignal-holdings already has.

## Structure

- `index.html` — now just a redirect to `articles/index.html` (the old marketing homepage
  with hero/services/$SIGNAL sections was retired; that content now lives on the separate
  factorysignal-holdings site instead). Don't rebuild a marketing homepage here.
- `articles/index.html` — the real homepage: sidebar (categories) + article grid feed
- `articles/*.html` — individual article pages
- `css/style.css`, `js/main.js` — shared styles/behavior

## Design language: Outstanding.kr-inspired, NOT the Holdings site's look

This is its own distinct media-brand identity — don't copy factorysignal-holdings' palette
here or vice versa without being asked.

- Accent color: bright blue `#1f8ce6` (Outstanding.kr's actual color, extracted from their
  real CSS — not the indigo `#4f46e5` used on factorysignal-holdings)
- Pretendard-led sans-serif, bold headlines, no serif anywhere
- Container `--max-w: 1600px` (widened from 1280px — was leaving large empty gutters on wide
  screens)
- Article cards: `.article-grid` is 4 columns (matches the 4 existing articles filling one
  row, Outstanding-style dense packing — don't drop back to 3 unless article count changes)
- Article thumbnails use a **category-colored gradient with bold text** (e.g. "TOKEN",
  "PRODUCT", "INFRA"), not a plain dark gradient — mimics Outstanding's colorful graphic
  thumbnails
- Byline row: small "FS" avatar circle + "factory Magazine 팀", bold/dark (not faint gray) —
  echoes Outstanding's author-forward card style

## Sidebar (articles/index.html)

Left sidebar replaced the old horizontal filter-tab row (same underlying `.filter-tab` class
and `data-filter` JS logic, just restyled/repositioned — don't reintroduce the horizontal row).
Order: 인기 포스팅 (전체) → 정치/경제/암호화폐/스포츠/세계/스타트업 → divider → 비즈니스
안내 / 멤버십결제 / 로그인·가입 (these three point at the live app / $SIGNAL article since
this site has no login or business-info pages of its own).

## Category colors (must match the main app one directory up — see `../CLAUDE.md`)

정치 purple `#6c5ce7` · 경제 green `#0ea968` · 암호화폐 amber `#d97706` · 스포츠 blue
`#3b82f6` · 세계 red `#e03040` · **스타트업 teal `#0d9488`** (magazine-only 6th category,
doesn't exist in the main app). All 4 current articles are tagged 암호화폐; 스타트업 has zero
articles so far (filtering it shows the existing "아직 이 카테고리의 아티클이 없습니다" empty
state — that's expected until someone actually publishes a startup-tagged post).

## Desktop nav fix

`.nav` used to be a mobile-style off-canvas drawer at ALL screen widths (no desktop
breakpoint existed). There's now a `@media (min-width: 769px)` override that shows a normal
inline horizontal nav and hides the hamburger/search icons above that width — don't remove it,
that was a real bug fix, not a style choice.
