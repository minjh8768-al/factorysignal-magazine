// 방문 통계 (관리자 페이지 '현황'용). 2026-10-20.
//   POST /api/track { path }   페이지를 열 때 main.js 가 한 번 보낸다.
//
// 저장: 날짜별 조회수(pv:YYYY-MM-DD), 방문자 수(uv:날짜, HyperLogLog — 개수만 세고 누구인지는
// 남지 않는다), 기사별 조회수(top:날짜). 방문자 구분값은 IP+날짜를 해시한 값이라 날마다 바뀌고
// IP 원문은 저장하지 않는다. 400일 뒤 자동 삭제.
const crypto = require('crypto');

const URL_ = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
const KEEP = 400 * 24 * 3600;
const BOT_RE = /bot|crawl|spider|slurp|headless|preview|facebookexternalhit|vercel/i;

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST' || !URL_ || !TOKEN) return res.status(204).end();
  if (BOT_RE.test(String(req.headers['user-agent'] || ''))) return res.status(204).end();
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const path = String(body.path || '/').slice(0, 200);
    const day = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);   // 한국 날짜
    const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
    const visitor = crypto.createHash('sha256').update(`${day}|${ip}|${req.headers['user-agent'] || ''}`).digest('hex').slice(0, 20);
    const slug = (path.match(/articles\/([a-z0-9-]+)\.html/) || [])[1] || '';
    const cmds = [
      ['INCR', `pv:${day}`], ['EXPIRE', `pv:${day}`, KEEP],
      ['PFADD', `uv:${day}`, visitor], ['EXPIRE', `uv:${day}`, KEEP],
    ];
    if (slug && !['index', 'all', 'subscribe', 'privacy'].includes(slug)) {
      cmds.push(['ZINCRBY', `top:${day}`, 1, slug], ['EXPIRE', `top:${day}`, KEEP]);
    }
    await fetch(`${URL_}/pipeline`, {
      method: 'POST', headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(cmds),
    });
  } catch (e) { /* 통계 실패가 페이지에 영향을 주면 안 된다 */ }
  return res.status(204).end();
};
