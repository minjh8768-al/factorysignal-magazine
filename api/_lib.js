// 예측 기능 공용 (2026-10-20). 밑줄로 시작하는 파일은 Vercel이 API 주소로 열지 않는다.
//  - kv(): Upstash Redis REST 파이프라인
//  - markets(): data/markets.json(4시간마다 tools/markets.py가 갱신) + Polymarket 실시간 확률
//  - session: 쿠키 fm_sid = "<uid>.<서명>". 처음 예측할 때 손님 id가 생기고, 로그인하면
//    같은 id에 계정이 붙는다(손님 때 한 예측이 그대로 남는다).
const crypto = require('crypto');

let DATA = { markets: [] };
try { DATA = require('../data/markets.json'); } catch (e) { /* 첫 수집 전 */ }

const URL_ = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
// 세션 서명 키. 따로 환경변수를 만들지 않도록 관리자 비밀번호에서 파생한다.
const SIGN_KEY = crypto.createHash('sha256').update(`fm-session|${process.env.SESSION_SECRET || process.env.MAGAZINE_ADMIN_SECRET || ''}`).digest();
const COOKIE = 'fm_sid';
const YEAR = 365 * 86400;

const ready = () => Boolean(URL_ && TOKEN && (process.env.SESSION_SECRET || process.env.MAGAZINE_ADMIN_SECRET));

async function kv(commands) {
  const r = await fetch(`${URL_}/pipeline`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(commands),
  });
  if (!r.ok) throw new Error(`redis ${r.status}`);
  return (await r.json()).map((x) => x.result);
}

const hpairs = (a) => { const o = {}; for (let i = 0; i + 1 < (a || []).length; i += 2) o[a[i]] = a[i + 1]; return o; };

// ── Polymarket 실시간 ─────────────────────────────────────────
let cache = { at: 0, list: null };
async function live(id) {
  const r = await fetch(`https://gamma-api.polymarket.com/markets/${id}`, { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(6000) });
  if (!r.ok) throw new Error(`gamma ${r.status}`);
  const m = await r.json();
  let p = NaN;
  try { p = Number(JSON.parse(m.outcomePrices || '[]')[0]); } catch (e) { /* 아래에서 처리 */ }
  return { closed: Boolean(m.closed), price: p };
}

// ── 독자 질문 (2026-10-21) ─────────────────────────────────────
// 로그인한 독자가 제안 → 관리자가 승인한 예/아니오 질문. 시장 확률 대신 독자 '예' 비율(market)을 쓴다.
// rq:{id} 해시(q, cat=분야, closesAt, how, by, byNick, status, outcome, final, resolvedAt, createdAt)
// rq:pending / rq:live / rq:resolved = 정렬 집합(점수 = 시각). 표는 Polymarket 질문과 같은 poll:pm-{id}.
const RQ_CAT = '독자 질문';
async function readerQuestions() {
  const [live, done] = await kv([['ZRANGE', 'rq:live', 0, -1], ['ZREVRANGE', 'rq:resolved', 0, 199]]);
  const ids = [...(live || []), ...(done || [])];
  if (!ids.length) return [];
  const rows = await kv(ids.flatMap((id) => [['HGETALL', `rq:${id}`], ['HGETALL', `poll:pm-${id}`]]));
  return ids.map((id, i) => {
    const r = hpairs(rows[2 * i]), c = hpairs(rows[2 * i + 1]);
    const yes = Number(c.yes) || 0, n = yes + (Number(c.no) || 0);
    const base = { id, q: r.q, cat: RQ_CAT, sub: r.cat || '', endDate: r.closesAt, addedAt: r.createdAt,
      kind: 'reader', by: r.byNick || '', how: r.how || '', voters: n };
    if (r.status === 'resolved') return { ...base, status: 'resolved', outcome: r.outcome, final: Number(r.final), resolvedAt: r.resolvedAt };
    const market = n ? Math.round((yes / n) * 1000) / 10 : null;
    // 랭킹 점수용 기준 확률: 표가 적을 때 한두 명의 표로 0%·100%가 되지 않게 50% 쪽으로 당긴다(가상 10표).
    const odds = Math.round(((yes + 5) / (n + 10)) * 1000) / 10;
    return { ...base, status: Date.parse(r.closesAt) < Date.now() ? 'closed' : 'live', market, odds };
  }).filter((x) => x.q);
}

// 모든 질문의 현재 상태. 진행 중인 것만 실시간 조회하고 60초간 재사용한다.
// status: live(진행 중) | closed(마감, 결과 확인 중) | resolved(결과 확정)
async function markets(fresh) {
  if (!fresh && cache.list && Date.now() - cache.at < 60e3) return cache.list;
  const pm = await Promise.all(DATA.markets.map(async (m) => {
    const base = { id: m.id, q: m.q, cat: m.cat, endDate: m.endDate, addedAt: m.addedAt };
    if (m.status === 'resolved') return { ...base, status: 'resolved', outcome: m.outcome, final: m.final, resolvedAt: m.resolvedAt };
    let g = null;
    try { g = await live(m.id); } catch (e) { /* 조회 실패 → 기록된 확률로 */ }
    if (g && g.closed) {
      if (g.price >= 0.99 || g.price <= 0.01) return { ...base, status: 'resolved', outcome: g.price >= 0.99 ? 'yes' : 'no', final: m.last, resolvedAt: '' };
      return { ...base, status: 'closed', market: m.last };
    }
    const market = g && g.price >= 0 && g.price <= 1 ? Math.round(g.price * 1000) / 10 : m.last;
    // 끝나는 시각이 지났으면 결과 확인 중으로 본다 (예측 받지 않음).
    if (Date.parse(m.endDate) < Date.now()) return { ...base, status: 'closed', market };
    return { ...base, status: 'live', market };
  }));
  let rq = [];
  try { rq = await readerQuestions(); } catch (e) { /* 독자 질문 없이도 */ }
  const list = [...pm, ...rq];
  cache = { at: Date.now(), list };
  return list;
}

// ── 세션 ─────────────────────────────────────────────────────
const sign = (uid) => crypto.createHmac('sha256', SIGN_KEY).update(uid).digest('base64url').slice(0, 22);

function readUid(req) {
  const m = String(req.headers.cookie || '').match(/(?:^|;\s*)fm_sid=([a-f0-9]{24})\.([\w-]{22})/);
  if (!m) return null;
  const a = Buffer.from(sign(m[1])), b = Buffer.from(m[2]);
  return a.length === b.length && crypto.timingSafeEqual(a, b) ? m[1] : null;
}

function setUid(res, uid) {
  res.setHeader('Set-Cookie', `${COOKIE}=${uid}.${sign(uid)}; Path=/; Max-Age=${YEAR}; HttpOnly; Secure; SameSite=Lax`);
}

function clearUid(res) {
  res.setHeader('Set-Cookie', `${COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`);
}

const newUid = () => crypto.randomBytes(12).toString('hex');

module.exports = { kv, hpairs, markets, readUid, setUid, clearUid, newUid, ready, DATA, RQ_CAT };
