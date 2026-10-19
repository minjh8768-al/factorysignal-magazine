document.addEventListener("DOMContentLoaded", () => {
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

    // 기사 → Factory Signal 모의 예측으로 넘기는 연결 고리. 가상 포인트라 돈이 들지
    // 않는다는 점을 문구에 분명히 한다(베팅 유도로 읽히지 않게).
    const cta = document.createElement("aside");
    cta.className = "predict-cta";
    const ctaTitle = document.createElement("strong");
    const ctaText = document.createElement("p");
    const ctaLink = document.createElement("a");
    ctaTitle.textContent = isEn
      ? "What odds does the world give this?"
      : "이 이슈, 세계는 몇 %로 보고 있을까요?";
    ctaText.textContent = isEn
      ? "See live prediction-market probabilities and make your own call with free virtual points."
      : "실제 예측시장 확률을 확인하고, 무료 가상 포인트로 직접 예측해 보세요.";
    ctaLink.href = "https://predictanalytics-news.vercel.app/#markets";
    ctaLink.textContent = isEn ? "Make a prediction →" : "모의 예측 하러 가기 →";
    cta.append(ctaTitle, ctaText, ctaLink);
    articleBody.append(cta);

    const notice = document.createElement("p");
    notice.className = "source-note ai-note";
    notice.textContent = isEn
      ? "This article was written with AI assistance and passed an automated fact-check. It is for information only, not investment advice."
      : "이 기사는 AI의 도움을 받아 작성했으며 자동 팩트체크를 거쳤습니다. 정보 제공용이며 투자 권유가 아닙니다.";
    articleBody.append(notice);
  }
});
