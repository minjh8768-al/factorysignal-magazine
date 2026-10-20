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
  document.querySelectorAll("form.subscribe-form").forEach(wireSubscribeForm);

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
    if (!isEn) mountInlineSubscribe(articleBody);

    const notice = document.createElement("p");
    notice.className = "source-note ai-note";
    notice.textContent = isEn
      ? "This article was written with AI assistance and passed an automated fact-check. It is for information only, not investment advice."
      : "이 기사는 AI의 도움을 받아 작성했으며 자동 팩트체크를 거쳤습니다. 정보 제공용이며 투자 권유가 아닙니다.";
    articleBody.append(notice);
  }
});

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
