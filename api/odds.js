// 첫 화면 '오늘의 확률' — 해외 예측시장(Polymarket) 확률.
//   GET /api/odds → { updatedAt, items: [{ key, question, category, market, endDate }] }
//
// 한국 IP에서는 Polymarket API가 막혀(451) 브라우저가 직접 부를 수 없다. 이 함수는 미국
// 리전에서 돌기 때문에 대신 가져온다. 질문 목록은 _odds-topics.json — 시장이 끝나면
// 그 파일에서 바꾼다(끝난 시장은 자동으로 빠진다). Polymarket으로 가는 링크는 일부러
// 넣지 않는다 (가입·베팅 유도로 읽히지 않게, 출처 표기만).
const topics = require('./_odds-topics.json');

async function fetchMarket(id) {
  // Gamma API의 목록 필터는 엉뚱한 시장을 돌려줄 때가 있어 단건 경로만 쓴다.
  const r = await fetch(`https://gamma-api.polymarket.com/markets/${id}`, {
    headers: { Accept: 'application/json' },
  });
  if (!r.ok) throw new Error(`gamma ${r.status}`);
  return r.json();
}

module.exports = async (req, res) => {
  const settled = await Promise.allSettled(topics.map((t) => fetchMarket(t.marketId)));
  const items = [];
  settled.forEach((s, i) => {
    if (s.status !== 'fulfilled') return;
    const m = s.value;
    if (m.closed || m.active === false) return;
    let yes;
    try { yes = Number(JSON.parse(m.outcomePrices || '[]')[0]); } catch { yes = NaN; }
    if (!(yes >= 0 && yes <= 1)) return;
    const t = topics[i];
    items.push({
      key: t.key,
      question: t.question,
      category: t.category,
      market: Math.round(yes * 1000) / 10,
      endDate: (m.endDate || '').slice(0, 10),
    });
  });
  // 10분간 CDN 캐시. 실패가 섞여도 나머지는 보여준다.
  res.setHeader('Cache-Control', 's-maxage=600, stale-while-revalidate=3600');
  res.json({ updatedAt: new Date().toISOString(), items });
};
