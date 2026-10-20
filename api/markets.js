// 첫 화면 예측 질문 (2026-10-20).
//   GET /api/markets → { updatedAt, live: [...], resolved: [...] }
//   각 항목: { id, q, cat, endDate, status, market(현재 '예' 확률 %), outcome, final, readers: {yes, no} }
// 질문 목록은 data/markets.json (tools/markets.py가 4시간마다 '핫한 10개'로 관리).
// 한국 IP는 Polymarket이 막지만 이 함수는 미국 리전에서 돈다. Polymarket 링크는 넣지 않는다.
const { kv, markets, hpairs, DATA } = require('./_lib');

const RESOLVED_SHOW = 12;

module.exports = async (req, res) => {
  try {
    const all = await markets();
    const live = all.filter((m) => m.status !== 'resolved')
      .sort((a, b) => (a.status === b.status ? 0 : a.status === 'live' ? -1 : 1));
    const resolved = all.filter((m) => m.status === 'resolved')
      .sort((a, b) => (b.resolvedAt || '9').localeCompare(a.resolvedAt || '9')).slice(0, RESOLVED_SHOW);
    const shown = [...live, ...resolved];
    let counts = [];
    try { counts = shown.length ? await kv(shown.map((m) => ['HGETALL', `poll:pm-${m.id}`])) : []; } catch (e) { /* 독자 수 없이도 보여 준다 */ }
    shown.forEach((m, i) => { const c = hpairs(counts[i]); m.readers = { yes: Number(c.yes) || 0, no: Number(c.no) || 0 }; });
    res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=600');
    res.json({ updatedAt: DATA.updatedAt || '', live, resolved });
  } catch (e) {
    res.status(500).json({ error: '예측 질문을 불러오지 못했습니다.' });
  }
};
