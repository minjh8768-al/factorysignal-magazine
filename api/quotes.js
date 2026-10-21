// 오른쪽 칸 '빠른 통계' (2026-10-21) — 비트코인 · S&P 500 · 원/달러 · VIX.
//   GET /api/quotes → { btc, sp500, krw, vix: { price, change, pct } }
// Yahoo Finance chart API는 CORS 헤더가 없어 브라우저가 직접 못 부른다. 미국 리전에서 대신
// 가져오고 5분간 CDN 캐시 (Factory Signal의 api/market-data.js와 같은 방식). 참고용, 지연 시세.
const SYMBOLS = { btc: 'BTC-USD', sp500: '%5EGSPC', krw: 'KRW%3DX', vix: '%5EVIX' };

async function quote(symbol) {
  const r = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${symbol}`, {
    headers: { 'User-Agent': 'Mozilla/5.0 (compatible; FactoryMagazine/1.0)' },
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`${symbol} ${r.status}`);
  const meta = (await r.json()).chart.result[0].meta;
  const price = meta.regularMarketPrice;
  const prev = meta.previousClose ?? meta.chartPreviousClose;
  return { price, change: price - prev, pct: prev ? ((price - prev) / prev) * 100 : 0 };
}

module.exports = async (req, res) => {
  const keys = Object.keys(SYMBOLS);
  const got = await Promise.allSettled(keys.map((k) => quote(SYMBOLS[k])));
  const out = {};
  got.forEach((g, i) => { if (g.status === 'fulfilled') out[keys[i]] = g.value; });
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=900');
  res.json(out);
};
