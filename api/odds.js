// 첫 화면 '오늘의 확률' — 해외 예측시장(Polymarket) 확률 + 우리 독자 전용 질문.
//   GET /api/odds → { updatedAt, items: [{ key, question, group, market, endDate, note, closesAt }] }
//
// 한국 IP에서는 Polymarket API가 막혀(451) 브라우저가 직접 부를 수 없다. 이 함수는 미국
// 리전에서 돌기 때문에 대신 가져온다. 질문 목록은 _odds-topics.json.
//  - marketId가 있으면 시장 확률을 붙인다. 시장이 끝나면 자동으로 빠진다.
//  - marketId가 없으면 '독자 예측 전용'(예: KBO처럼 해외 시장이 없는 한국 이슈). market은 null.
//    closesAt(UTC)이 지나면 투표가 막히고, 그 뒤 SHOW_AFTER_CLOSE_H시간까지만 결과를 보여 준다.
// Polymarket으로 가는 링크는 일부러 넣지 않는다 (가입·베팅 유도로 읽히지 않게, 출처 표기만).
const topics = require('./_odds-topics.json');

const SHOW_AFTER_CLOSE_H = 12;
// 탭(group)마다 보여 줄 최대 개수. 운영 원칙: 분야별 주제는 3개. 목록에 더 적어 두면
// 앞의 질문이 끝났을 때 다음 것이 자동으로 채워진다.
const PER_GROUP = 3;

async function fetchMarket(id) {
  // Gamma API의 목록 필터는 엉뚱한 시장을 돌려줄 때가 있어 단건 경로만 쓴다.
  const r = await fetch(`https://gamma-api.polymarket.com/markets/${id}`, {
    headers: { Accept: 'application/json' },
  });
  if (!r.ok) throw new Error(`gamma ${r.status}`);
  return r.json();
}

module.exports = async (req, res) => {
  const now = Date.now();
  const settled = await Promise.allSettled(
    topics.map((t) => (t.marketId ? fetchMarket(t.marketId) : Promise.resolve(null))),
  );
  const items = [];
  settled.forEach((s, i) => {
    const t = topics[i];
    const base = { key: t.key, question: t.question, group: t.group, note: t.note || '', closesAt: t.closesAt || '' };

    if (!t.marketId) {
      const close = t.closesAt ? Date.parse(t.closesAt) : NaN;
      if (close && now > close + SHOW_AFTER_CLOSE_H * 3600e3) return;
      items.push({ ...base, market: null, endDate: '' });
      return;
    }

    if (s.status !== 'fulfilled') return;
    const m = s.value;
    if (m.closed || m.active === false) return;
    // 보통 0번이 'Yes'. 두 팀 경기 시장은 결과가 [팀A, 팀B]라서 우리 질문의 팀 쪽 번호를 쓴다.
    let yes;
    try { yes = Number(JSON.parse(m.outcomePrices || '[]')[t.outcomeIndex || 0]); } catch { yes = NaN; }
    if (!(yes >= 0 && yes <= 1)) return;
    items.push({ ...base, market: Math.round(yes * 1000) / 10, endDate: (m.endDate || '').slice(0, 10) });
  });
  const perGroup = {};
  const capped = items.filter((it) => (perGroup[it.group] = (perGroup[it.group] || 0) + 1) <= PER_GROUP);
  // 5분간 CDN 캐시. 실패가 섞여도 나머지는 보여준다.
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=1800');
  res.json({ updatedAt: new Date().toISOString(), items: capped });
};
