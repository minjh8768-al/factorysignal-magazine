// Vercel Web Analytics. 기사 수백 편에 태그를 일일이 넣지 않고 공용 스크립트에서 붙인다.
// /blog 아래로 프록시돼 열리면 Factory Signal 프로젝트의 분석에, 매거진 주소로 직접
// 열리면 매거진 프로젝트의 분석에 잡힌다 (각 프로젝트에서 Analytics를 켜 둬야 집계됨).
(() => {
  window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
  const s = document.createElement("script");
  s.defer = true;
  s.src = "/_vercel/insights/script.js";
  document.head.append(s);
})();

// 매거진이 predictanalytics-news 도메인의 /blog 아래로 프록시돼 열릴 때도 매거진 API에 닿게 한다.
function apiUrl(name) {
  return (location.pathname.startsWith("/blog/") ? "/blog" : "") + "/api/" + name;
}

document.addEventListener("DOMContentLoaded", () => {
  // 관리자 페이지 '현황'용 방문 집계 (api/track.js). 개인을 알아볼 수 없게 센다.
  try {
    navigator.sendBeacon(apiUrl("track"), new Blob([JSON.stringify({ path: location.pathname })], { type: "text/plain" }));
  } catch (e) { /* 통계가 실패해도 페이지는 그대로 */ }

  document.querySelectorAll("form.subscribe-form").forEach(wireSubscribeForm);
  // 전체 기사(all.html?cat=경제): 첫 화면 분야 링크로 들어오면 그 분야 필터를 켠 채로 연다.
  const catParam = new URLSearchParams(location.search).get("cat");
  if (catParam) {
    // 필터 버튼의 클릭 처리기는 이 함수 아래쪽에서 붙으므로 한 박자 뒤에 누른다.
    setTimeout(() => {
      const tab = [...document.querySelectorAll(".filter-tab")].find((t) => t.dataset.filter === catParam);
      if (tab) tab.click();
    }, 0);
  }

  // 첫 화면 날짜: 한국 시간 기준 "10월 20일 화요일 오후의 예측"
  const briefDate = document.getElementById("brief-date");
  if (briefDate) {
    const now = new Date();
    const day = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric", weekday: "long" }).format(now);
    const hour = Number(new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Seoul", hour: "numeric", hourCycle: "h23" }).format(now));
    const part = hour < 12 ? "아침" : hour < 18 ? "오후" : "저녁";
    briefDate.textContent = `${day} ${part}의 예측`;
  }
  if (document.getElementById("pm-live") || document.getElementById("pm-resolved")) mountMarkets();
  const artMarket = document.querySelector(".mk-article-market[data-market]");
  if (artMarket) mountArticleMarket(artMarket);
  if (document.getElementById("pf-head")) mountProfile();

  const nav = document.querySelector(".nav");
  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");

  const onScroll = () => {
    if (window.scrollY > 40) {
      nav.classList.add("solid");
    } else {
      nav.classList.remove("solid");
    }
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  if (toggle && links) {
    toggle.addEventListener("click", () => {
      toggle.classList.toggle("open");
      links.classList.toggle("open");
    });

    links.querySelectorAll("a").forEach((a) => {
      a.addEventListener("click", () => {
        toggle.classList.remove("open");
        links.classList.remove("open");
      });
    });
  }

  const filterTabs = document.querySelectorAll(".filter-tab");
  const articleCards = document.querySelectorAll(".article-card[data-category]");
  const emptyNotice = document.querySelector(".article-empty");

  if (filterTabs.length && articleCards.length) {
    filterTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        filterTabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");

        const category = tab.dataset.filter;
        let visibleCount = 0;

        articleCards.forEach((card) => {
          const show = category === "전체" || card.dataset.category === category;
          card.classList.toggle("is-hidden", !show);
          if (show) visibleCount++;
        });

        if (emptyNotice) {
          emptyNotice.style.display = visibleCount === 0 ? "block" : "none";
        }
      });
    });
  }

  // 기사 페이지: 발행일과 AI 작성 표기. 이미 발행된 기사 수백 편을 다시 쓰지 않고
  // 한 곳에서 붙이려고 JS로 넣는다. 발행일은 publish.py가 심는 fs:date 메타에서 읽는다.
  const articleBody = document.querySelector("article.article-content");
  if (articleBody) {
    const isEn = document.documentElement.lang === "en";
    const dateMeta = document.querySelector('meta[name="fs:date"]');
    const heroMeta = document.querySelector(".article-hero .article-meta");
    if (dateMeta && heroMeta && !heroMeta.querySelector("time")) {
      const time = document.createElement("time");
      time.dateTime = dateMeta.content;
      time.textContent = dateMeta.content.replace(/-/g, ".");
      heroMeta.append(" · ", time);
    }

    const pollMeta = document.querySelector('meta[name="fs:poll"]');
    if (pollMeta && pollMeta.content) mountPoll(articleBody, pollMeta.content);
    // 2026-10-20: 기사 하단 뉴스레터 박스는 뺐다 (구독자 모으기는 당분간 목표가 아님).

    const notice = document.createElement("p");
    notice.className = "source-note ai-note";
    // 예측 기사(fs:market)는 자동 팩트체크 대신 편집자 승인을 거쳐 발행된다.
    const isMarket = !!document.querySelector('meta[name="fs:market"]');
    notice.textContent = isEn
      ? "This article was written with AI assistance and passed an automated fact-check. It is for information only, not investment advice."
      : isMarket
        ? "이 기사는 AI의 도움을 받아 작성했으며 편집자가 확인한 뒤 발행했습니다. 정보 제공용이며 투자·베팅 권유가 아닙니다."
        : "이 기사는 AI의 도움을 받아 작성했으며 자동 팩트체크를 거쳤습니다. 정보 제공용이며 투자 권유가 아닙니다.";
    articleBody.append(notice);
  }
});

// ── 첫 화면 예측 (2026-10-20 개편) ─────────────────────────────────────
// 질문·확률은 api/markets.js(미국 리전에서 Polymarket 조회, 핫한 10개), 내 예측은 api/me.js.
// 예측은 질문당 한 번이고 바꿀 수 없다. 독자 비율은 내가 고른 뒤, READER_MIN명 이상일 때만
// 보여 준다(먼저 보면 따라가게 되고, 1~2명일 때의 100%·0%는 의미가 없어서).
const READER_MIN = 10;
const pct = (n) => `${Math.round(n)}%`;
const choiceKo = (c) => (c === "yes" ? "예" : "아니오");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function dday(iso) {
  const ms = Date.parse(iso) - Date.now();
  if (!(ms > 0)) return "마감";
  const h = ms / 3600e3;
  if (h < 24) return `${Math.max(1, Math.round(h))}시간 남음`;
  return `D-${Math.ceil(h / 24)}`;
}

function readersLine(r, mine) {
  const total = ((r && r.yes) || 0) + ((r && r.no) || 0);
  if (!mine) return "";
  if (total < READER_MIN) return `독자 ${total}명 참여 · ${READER_MIN}명부터 비율 공개`;
  return `독자 ${pct((r.yes / total) * 100)}가 예 (${total.toLocaleString()}명)`;
}

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(d.error || `오류 ${r.status}`), { status: r.status });
  return d;
}

// 분야 탭. 세 구역(진행 중 · 결과 · 기사)이 같은 분야 순서를 쓴다. 해당 분야에 항목이 없으면 탭도 없다.
const MKT_CATS = ["경제", "코인", "정치·세계", "스포츠", "테크·문화"];
const OLD_CAT = { "경제": "경제", "코인": "암호화폐", "정치·세계": "정치", "스포츠": "스포츠", "테크·문화": "스타트업" };

function catTabs(box, cats, onPick) {
  if (!box) return;
  const present = MKT_CATS.filter((c) => cats.includes(c));
  box.innerHTML = ["전체", ...present].map((c) => `<button type="button" data-cat="${c}">${c}</button>`).join("");
  const pick = (c) => {
    box.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.cat === c));
    onPick(c);
  };
  box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => pick(b.dataset.cat)));
  pick("전체");
}

// 기사 구역: publish.py가 카드(data-cat)와 질문별 기사 목록(#mk-links)을 미리 심어 둔다.
function mountArticles(markets) {
  const grid = document.getElementById("mk-grid");
  if (!grid) return;
  const cards = [...grid.querySelectorAll(".mk-art")];
  const more = document.getElementById("mk-more");
  catTabs(document.getElementById("tabs-articles"), cards.map((c) => c.dataset.cat), (cat) => {
    let n = 0;
    cards.forEach((c) => {
      const show = (cat === "전체" || c.dataset.cat === cat) && n < (document.getElementById("pm-live") ? 12 : Infinity);
      if (show) n++;
      c.hidden = !show;
    });
    if (more) more.href = cat === "전체" ? "all.html" : `all.html?cat=${encodeURIComponent(OLD_CAT[cat])}`;
  });
  // 예측 기사 카드에 연결된 질문의 지금 상태를 붙인다.
  const byId = Object.fromEntries(markets.map((m) => [m.id, m]));
  grid.querySelectorAll(".mk-chip[data-market]").forEach((chip) => {
    const m = byId[chip.dataset.market];
    if (!m) return;
    chip.classList.add(m.status === "resolved" ? "is-done" : "is-live");
    chip.textContent = m.status === "resolved"
      ? `결과 ${choiceKo(m.outcome)} · 마감 전 ${pct(m.final)}`
      : `진행 중 · 시장 ${pct(m.market)}`;
  });
}

function marketLinks() {
  try { return JSON.parse(document.getElementById("mk-links").textContent || "{}"); } catch (e) { return {}; }
}

async function mountMarkets() {
  const liveEl = document.getElementById("pm-live");
  const resEl = document.getElementById("pm-resolved");
  let data, me;
  try {
    [data, me] = await Promise.all([
      getJSON(apiUrl("markets") + (liveEl ? "" : "?all=1")),
      getJSON(apiUrl("me"), { credentials: "same-origin" }).catch(() => ({ preds: [] })),
    ]);
  } catch (e) {
    mountArticles([]);   // 확률을 못 불러와도 기사 탭은 동작하게
    if (!liveEl) { resEl.innerHTML = '<p class="odds-empty">지금은 불러올 수 없어요. 잠시 후 다시 확인해 주세요.</p>'; return; }
    liveEl.innerHTML = '<p class="odds-empty">지금은 질문을 불러올 수 없어요. 잠시 후 다시 확인해 주세요.</p>';
    resEl.innerHTML = "";
    return;
  }
  const mine = Object.fromEntries((me.preds || []).map((p) => [p.id, p]));

  const links = marketLinks();
  const liveCards = data.live.map((m) => liveCard(m, mine[m.id], links[m.id] || []));
  const resRows = data.resolved.map((m) => resultRow(m, mine[m.id], links[m.id] || []));
  const fill = (el, items, list, empty) => (cat) => {
    const limit = Number(el.dataset.limit) || Infinity;   // 첫 화면 결과는 6개(3칸 × 2줄)만
    el.innerHTML = "";
    items.forEach((node, i) => {
      if ((cat === "전체" || list[i].cat === cat) && el.children.length < limit) el.append(node);
    });
    if (!el.children.length) el.innerHTML = `<p class="odds-empty">${empty}</p>`;
  };
  if (liveEl) catTabs(document.getElementById("tabs-live"), data.live.map((m) => m.cat),
    fill(liveEl, liveCards, data.live, "새 질문을 고르는 중이에요."));
  catTabs(document.getElementById("tabs-resolved"), data.resolved.map((m) => m.cat),
    fill(resEl, resRows, data.resolved, "아직 결과가 나온 질문이 없어요."));
  mountArticles([...data.live, ...data.resolved]);
}

// 반원 게이지. 시장이 '예'에 매긴 확률을 호의 길이로 보여 준다. 숫자도 함께 적어 색에만 기대지 않는다.
function gauge(p) {
  const r = 34, len = Math.PI * r;
  const on = Math.max(0, Math.min(100, p)) / 100 * len;
  return `<svg class="pm-gauge" viewBox="0 0 84 50" role="img" aria-label="시장이 본 '예' 확률 ${pct(p)}">
    <path d="M8 44 A34 34 0 0 1 76 44" class="g-bg"/>
    <path d="M8 44 A34 34 0 0 1 76 44" class="g-on" stroke-dasharray="${on} ${len}"/>
    <text x="42" y="40" class="g-num">${pct(p)}</text></svg>`;
}

function relLink(arts, kind) {
  const a = arts.find((x) => x.kind === kind) || arts[0];
  if (!a) return "";
  const label = kind === "result" ? "결과 기사" : "관련 기사";
  return `<a class="pm-rel" href="${esc(a.slug)}.html">${label}${arts.length > 1 ? ` ${arts.length}편` : ""} →</a>`;
}

function liveCard(m, my, arts = []) {
  const el = document.createElement("article");
  el.className = "pm-card";
  const open = m.status === "live";
  el.innerHTML = `
    <div class="pm-main">
      <div class="pm-text">
        <div class="pm-meta"><span class="pm-cat">${esc(m.cat)}</span><span>·</span><span>${open ? dday(m.endDate) : "결과 확인 중"}</span></div>
        <h3 class="pm-q">${esc(m.q)}</h3>
      </div>
      <div class="pm-g">${gauge(m.market)}<span>가능성</span></div>
    </div>
    <div class="pm-foot"><div class="pm-actions"></div>${relLink(arts, "preview")}</div>`;
  const actions = el.querySelector(".pm-actions");
  const showMine = (choice, readers, odds) => {
    actions.innerHTML = `<span class="pm-mine">내 예측 <b>${choiceKo(choice)}</b>${odds != null ? ` · 고를 때 시장 ${pct(odds)}` : ""}</span><span class="pm-readers">${esc(readersLine(readers, choice))}</span>`;
  };
  if (my) { showMine(my.choice, m.readers, my.pickedOdds); return el; }
  if (!open) { actions.innerHTML = '<span class="pm-readers">예측 마감</span>'; return el; }
  actions.innerHTML = '<button type="button" data-c="yes">예</button><button type="button" data-c="no">아니오</button>';
  actions.querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
    actions.querySelectorAll("button").forEach((x) => (x.disabled = true));
    try {
      const d = await getJSON(apiUrl("me"), {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "predict", id: m.id, choice: b.dataset.c }),
      });
      showMine(b.dataset.c, d.readers, b.dataset.c === "yes" ? m.market : 100 - m.market);
    } catch (e) {
      actions.querySelectorAll("button").forEach((x) => (x.disabled = false));
      if (e.status === 401) return showLogin(actions);
      const err = document.createElement("span");
      err.className = "pm-readers";
      err.textContent = e.message;
      actions.append(err);
    }
  }));
  return el;
}

// 로그인해야 예측할 수 있다 (2026-10-20). 로그인하고 나면 첫 화면으로 돌아온다.
let authStatus = null;
async function showLogin(actions) {
  if (actions.querySelector(".pm-login")) return;
  authStatus = authStatus || (await getJSON(`${apiUrl("auth")}?status=1`).catch(() => ({})));
  const next = encodeURIComponent(location.pathname.replace(/^\/blog/, ""));
  const btn = (p, label) => authStatus[p]
    ? `<a class="pf-btn pf-${p}" href="${apiUrl("auth")}?start=${p}&next=${next}">${label}</a>`
    : `<span class="pf-btn pf-${p} is-off">${label} (준비 중)</span>`;
  const box = document.createElement("div");
  box.className = "pm-login";
  box.innerHTML = `<p>로그인하면 예측하고, 적중 기록을 모을 수 있어요.</p><div class="pf-login">${btn("kakao", "카카오로 로그인")}${btn("google", "Google로 로그인")}</div>`;
  actions.after(box);
}

// 결과 카드. 시장이 50% 미만으로 본 쪽이 실제로 일어났으면 '이변' 표시.
function resultRow(m, my, arts = []) {
  const el = document.createElement("article");
  el.className = "pm-rcard";
  const total = (m.readers.yes || 0) + (m.readers.no || 0);
  const readers = total >= READER_MIN ? ` · 독자 ${pct((m.readers.yes / total) * 100)} 예` : "";
  const badge = my ? (my.choice === m.outcome ? '<span class="pm-win">적중</span>' : '<span class="pm-lose">빗나감</span>') : "";
  const sideOdds = m.final == null ? null : m.outcome === "yes" ? m.final : 100 - m.final;
  const upset = sideOdds != null && sideOdds < 50 ? '<span class="pm-upset">이변</span>' : "";
  const day = (m.resolvedAt || "").slice(5, 10).replace("-", ".");
  el.innerHTML = `
    <div class="pm-rtop"><span class="pm-outcome is-${m.outcome}">결과 ${choiceKo(m.outcome)}</span>${upset}<span class="pm-rmeta">${esc(m.cat)}${day ? ` · ${day}` : ""}</span></div>
    <strong class="pm-rq">${esc(m.q)}</strong>
    <span class="pm-rodds">${m.final != null ? `시장은 마감 전 '예'를 <b>${pct(m.final)}</b>로 봤어요` : "결과 확정"}${readers}</span>
    <div class="pm-rfoot">${my ? `<span class="pm-rmine">내 예측 ${choiceKo(my.choice)}</span>${badge}` : ""}${relLink(arts, "result")}</div>`;
  return el;
}

// 예측 기사 안의 질문 카드 (2026-10-21). 기사를 읽다가 바로 예측하거나 결과를 볼 수 있게.
async function mountArticleMarket(box) {
  try {
    const [data, me] = await Promise.all([
      getJSON(apiUrl("markets") + "?all=1"),
      getJSON(apiUrl("me"), { credentials: "same-origin" }).catch(() => ({ preds: [] })),
    ]);
    const m = [...data.live, ...data.resolved].find((x) => x.id === box.dataset.market);
    if (!m) return;
    const my = (me.preds || []).find((p) => p.id === m.id);
    const label = document.createElement("p");
    label.className = "mk-article-label";
    label.textContent = m.status === "resolved" ? "이 기사의 예측 질문 · 결과" : "이 기사의 예측 질문 · 지금 확률";
    box.append(label, m.status === "resolved" ? resultRow(m, my) : liveCard(m, my));
  } catch (e) { /* 카드 없이도 기사는 읽힌다 */ }
}

// ── 내 예측 기록 (profile.html) ─────────────────────────────────────
async function mountProfile() {
  const head = document.getElementById("pf-head");
  const tiles = document.getElementById("pf-tiles");
  const list = document.getElementById("pf-list");
  const tabs = document.getElementById("pf-tabs");
  let me, auth;
  try {
    [me, auth] = await Promise.all([
      getJSON(apiUrl("me"), { credentials: "same-origin" }),
      getJSON(`${apiUrl("auth")}?status=1`).catch(() => ({})),
    ]);
  } catch (e) {
    head.innerHTML = `<p class="odds-empty">${esc(e.message)}</p>`;
    return;
  }
  const loginMsg = { ok: "로그인했어요.", failed: "로그인에 실패했어요. 다시 시도해 주세요.", unavailable: "이 로그인은 아직 준비 중이에요." }[new URLSearchParams(location.search).get("login")] || "";
  const btn = (p, label) => auth[p]
    ? `<a class="pf-btn pf-${p}" href="${apiUrl("auth")}?start=${p}">${label}</a>`
    : `<span class="pf-btn pf-${p} is-off">${label} (준비 중)</span>`;
  const loginButtons = `<div class="pf-login">${btn("kakao", "카카오로 계속하기")}${btn("google", "Google로 계속하기")}</div>`;
  const u = me.user;
  if (!u) {
    head.innerHTML = `<h1>내 예측 기록</h1><p class="pf-lead">로그인하면 예측할 수 있고, 적중률과 기록이 여기에 쌓여요.</p>${loginButtons}<p class="pf-msg">${esc(loginMsg)}</p>`;
  } else {
    const via = u.provider === "kakao" ? "카카오" : "Google";
    head.innerHTML = `
      <h1><span id="pf-nick">${esc(u.nick)}</span> <button type="button" class="pf-edit" id="pf-edit">닉네임 바꾸기</button></h1>
      <p class="pf-lead">${u.provider ? `${via} 계정으로 로그인됨 · <a href="#" id="pf-logout">로그아웃</a>` : "손님으로 예측 중이에요. 로그인하면 이 기록이 계정에 저장돼 다른 기기에서도 볼 수 있어요."}</p>
      ${u.provider ? "" : loginButtons}<p class="pf-msg">${esc(loginMsg)}</p>`;
    document.getElementById("pf-edit").onclick = async () => {
      const nick = prompt("새 닉네임 (2~12자)", u.nick);
      if (!nick) return;
      try {
        await getJSON(apiUrl("me"), { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "nick", nick }) });
        document.getElementById("pf-nick").textContent = nick.trim();
      } catch (e) { alert(e.message); }
    };
    const out = document.getElementById("pf-logout");
    if (out) out.onclick = async (e) => {
      e.preventDefault();
      await fetch(apiUrl("me"), { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "logout" }) });
      location.href = "profile.html";
    };
  }

  const s = me.stats;
  tiles.innerHTML = [
    ["적중률", s.accuracy == null ? "–" : `${s.accuracy}%`, s.resolved ? `결과 나온 ${s.resolved}개 중` : "결과가 나오면 계산돼요"],
    ["적중", s.wins, `연속 ${s.streak} · 최고 연속 ${s.best}`],
    ["역발상 적중", s.upset, "시장이 50% 미만으로 본 쪽을 맞힘"],
    ["예측한 질문", s.total, `진행 중 ${s.open}`],
  ].map(([l, v, sub]) => `<div class="pf-tile"><div class="pf-label">${l}</div><div class="pf-value">${v}</div><div class="pf-sub">${sub}</div></div>`).join("");

  const draw = (t) => {
    tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.t === t));
    const rows = me.preds.filter((p) => (t === "open" ? p.result === "open" : p.result !== "open"));
    list.innerHTML = rows.length ? rows.map((p) => {
      const badge = p.result === "win" ? '<span class="pm-win">적중</span>'
        : p.result === "lose" ? '<span class="pm-lose">빗나감</span>'
        : p.status === "closed" ? '<span class="pm-wait">결과 확인 중</span>'
        : p.result === "unknown" ? '<span class="pm-wait">확인 불가</span>'
        : `<span class="pm-wait">${p.market != null ? `지금 시장 ${pct(p.market)}` : ""}</span>`;
      return `<div class="pf-row"><div><strong>${esc(p.q)}</strong>
        <span>${esc(p.cat)} · 내 예측 <b>${choiceKo(p.choice)}</b> · 고를 때 시장 ${pct(p.pickedOdds)}${p.outcome ? ` · 결과 ${choiceKo(p.outcome)}` : ""}</span></div>${badge}</div>`;
    }).join("") : `<p class="odds-empty">${t === "open" ? "진행 중인 예측이 없어요." : "아직 결과가 나온 예측이 없어요."}</p>`;
  };
  tabs.querySelectorAll("button").forEach((b) => (b.onclick = () => draw(b.dataset.t)));
  draw("open");
}

// ── 뉴스레터 구독 ───────────────────────────────────────────────────
// 구독 페이지와 기사 하단 박스가 같은 처리기를 쓴다. 저장은 api/subscribe.js.
function wireSubscribeForm(form) {
  const status = form.querySelector(".subscribe-status");
  const button = form.querySelector('button[type="submit"]');
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const letters = [...form.querySelectorAll('input[name="letters"]')]
      .filter((i) => i.checked || i.type === "hidden").map((i) => i.value);
    const email = form.querySelector('input[name="email"]').value.trim();
    const consent = form.querySelector('input[name="consent"]').checked;
    const say = (msg, ok) => { status.textContent = msg; status.classList.toggle("is-ok", !!ok); };
    if (!letters.length) return say("받아볼 뉴스레터를 하나 이상 골라 주세요.");
    if (!email) return say("이메일 주소를 입력해 주세요.");
    if (!consent) return say("개인정보 수집·이용에 동의해 주세요.");
    button.disabled = true;
    try {
      const r = await fetch(apiUrl("subscribe"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, letters, consent, source: form.dataset.source || "" }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.status === 503) throw new Error("뉴스레터는 곧 시작합니다. 조금만 기다려 주세요!");
      if (!r.ok) throw new Error(data.error || "구독 처리 중 오류가 났습니다.");
      form.reset();
      say("구독 신청이 완료됐어요. 첫 메일에서 만나요!", true);
    } catch (err) {
      say(err.message);
    } finally {
      button.disabled = false;
    }
  });
}

function mountInlineSubscribe(container) {
  const box = document.createElement("aside");
  box.className = "subscribe-inline";
  box.innerHTML = `
    <strong>매일 아침, 확률로 읽는 뉴스 3분</strong>
    <p>세계 예측시장이 본 확률 5개와 3줄 요약을 메일로 받아보세요.</p>
    <form class="subscribe-form" data-source="article-end" novalidate>
      <input type="hidden" name="letters" value="daily" />
      <div class="subscribe-line">
        <input class="subscribe-email" type="email" name="email" placeholder="이메일 주소" autocomplete="email" />
        <button type="submit" class="subscribe-submit">구독하기</button>
      </div>
      <label class="subscribe-consent">
        <input type="checkbox" name="consent" />
        <span>[필수] 뉴스레터 발송을 위한 이메일 수집·이용에 동의합니다. 해지 시 즉시 파기합니다. <a href="privacy.html" target="_blank" rel="noopener">자세히</a></span>
      </label>
      <p class="subscribe-status" role="status"></p>
    </form>`;
  container.append(box);
  wireSubscribeForm(box.querySelector("form"));
}

// ── 기사 하단 예/아니오 투표 ─────────────────────────────────────────
// 질문은 기사 생성 때 fs:poll 메타로 심긴다. 로그인 없이 한 번 누르면 독자 비율을 보여준다.
// 저장은 api/vote.js. 매거진이 /blog 아래로 프록시돼 열릴 때도 같은 API에 닿도록 경로를 맞춘다.
function mountPoll(container, question) {
  const slug = location.pathname.split("/").pop().replace(/\.html$/, "");
  const api = apiUrl("vote");
  const storeKey = `fm-poll:${slug}`;

  const box = document.createElement("aside");
  box.className = "poll-box";
  const label = document.createElement("span");
  label.className = "poll-label";
  label.textContent = "독자 투표";
  const q = document.createElement("strong");
  q.className = "poll-question";
  q.textContent = question;
  const buttons = document.createElement("div");
  buttons.className = "poll-buttons";
  const result = document.createElement("div");
  result.className = "poll-result";
  const note = document.createElement("p");
  note.className = "poll-note";
  note.textContent = "로그인 없이 참여할 수 있습니다. 결과는 독자들의 생각이며 예측이나 권유가 아닙니다.";

  const choices = [["yes", "예"], ["no", "아니오"]];
  choices.forEach(([value, text]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.addEventListener("click", () => vote(value));
    buttons.append(b);
  });
  box.append(label, q, buttons, result, note);
  container.append(box);

  function show(data, mine) {
    const total = (data.yes || 0) + (data.no || 0);
    const pct = (n) => (total ? Math.round((n / total) * 100) : 0);
    buttons.hidden = true;
    result.innerHTML = "";
    choices.forEach(([value, text]) => {
      const row = document.createElement("div");
      row.className = "poll-row" + (value === mine ? " is-mine" : "");
      const name = document.createElement("span");
      name.textContent = text + (value === mine ? " ✓" : "");
      const bar = document.createElement("span");
      bar.className = "poll-bar";
      const fill = document.createElement("span");
      fill.style.width = pct(data[value] || 0) + "%";
      bar.append(fill);
      const num = document.createElement("span");
      num.textContent = pct(data[value] || 0) + "%";
      row.append(name, bar, num);
      result.append(row);
    });
    const count = document.createElement("p");
    count.className = "poll-count";
    count.textContent = `${total.toLocaleString()}명 참여`;
    result.append(count);
  }

  async function vote(choice) {
    buttons.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      const r = await fetch(api, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug, choice }),
      });
      if (!r.ok) throw new Error();
      localStorage.setItem(storeKey, choice);
      show(await r.json(), choice);
    } catch (e) {
      buttons.querySelectorAll("button").forEach((b) => (b.disabled = false));
      note.textContent = "지금은 투표를 받을 수 없습니다. 잠시 후 다시 시도해 주세요.";
    }
  }

  // 이미 투표한 브라우저면 결과부터 보여준다. 저장소가 아직 없으면(503) 투표 박스를 숨긴다.
  const mine = localStorage.getItem(storeKey);
  fetch(`${api}?slug=${encodeURIComponent(slug)}`)
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((data) => { if (mine) show(data, mine); })
    .catch((status) => { if (status === 503) box.remove(); });
}
