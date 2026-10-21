// 내 예측과 프로필 (2026-10-20).
//   GET  /api/me                              → { user, stats, preds }  (예측한 적 없으면 user: null)
//   POST /api/me { action:'predict', id, choice:'yes'|'no' }   가상 예측 (질문당 한 번, 바꿀 수 없음)
//        2026-10-20 사용자 결정: 로그인(구글·카카오)해야 예측할 수 있다. 아니면 401.
//   POST /api/me { action:'nick', nick }      닉네임 바꾸기
//   POST /api/me { action:'logout' }
//   POST /api/me { action:'propose', q, cat, closesAt, how }   독자 질문 제안 (로그인, 하루 3개, 관리자 승인 후 공개)
//   GET  /api/me?view=rank&period=week|lastweek|month          주간·월간 랭킹 (+ 내 순위)
// 랭킹 점수(2026-10-21): 맞히면 100 − (고를 때 내가 고른 쪽 확률), 틀리면 0. 시장을 따라가기보다
// 시장보다 먼저 맞힌 사람이 위로 가게. 독자 질문은 시장 확률 대신 고를 때의 독자 '예' 비율.
// 돈·포인트는 없다. 예/아니오를 골라 두고 결과가 나면 맞혔는지만 센다.
// 저장(Upstash): user:{uid} 해시(nick, createdAt, provider), pred:{uid} 해시(질문id → {c, at, p}),
//               poll:pm-{id} 해시(yes/no 독자 수).
const crypto = require('crypto');
const { kv, hpairs, markets, readUid, clearUid, ready } = require('./_lib');

const NICK_RE = /^[\p{L}\p{N}_.\- ]{2,12}$/u;

function stats(preds) {
  const done = preds.filter((p) => p.result === 'win' || p.result === 'lose')
    .sort((a, b) => (a.resolvedAt || '').localeCompare(b.resolvedAt || ''));
  const wins = done.filter((p) => p.result === 'win').length;
  let streak = 0, best = 0, run = 0;
  done.forEach((p) => { run = p.result === 'win' ? run + 1 : 0; best = Math.max(best, run); });
  for (let i = done.length - 1; i >= 0 && done[i].result === 'win'; i--) streak++;
  // 역발상 적중: 고를 때 시장이 50% 미만으로 본 쪽을 골라 맞힌 것
  const upset = done.filter((p) => p.result === 'win' && p.pickedOdds < 50).length;
  return {
    total: preds.length, open: preds.length - done.length, resolved: done.length, wins,
    accuracy: done.length ? Math.round((wins / done.length) * 100) : null, streak, best, upset,
  };
}

async function profile(uid) {
  const [u, raw] = await kv([['HGETALL', `user:${uid}`], ['HGETALL', `pred:${uid}`]]);
  const user = hpairs(u);
  const picks = hpairs(raw);
  const byId = Object.fromEntries((await markets()).map((m) => [m.id, m]));
  const preds = Object.entries(picks).map(([id, v]) => {
    const p = JSON.parse(v);
    const m = byId[id] || { id, q: p.q || '(목록에서 내려간 질문)', status: 'gone' };
    // 고를 때 내가 고른 쪽의 시장 확률
    const base = p.p == null ? 50 : p.p;            // 독자 질문 첫 표처럼 기준 확률이 없으면 50
    const pickedOdds = p.c === 'yes' ? base : Math.round((100 - base) * 10) / 10;
    const result = m.status === 'resolved' ? (m.outcome === p.c ? 'win' : 'lose') : m.status === 'gone' ? 'unknown' : 'open';
    return { id, q: m.q, cat: m.cat || '', choice: p.c, at: p.at, pickedOdds, market: m.market ?? null,
      status: m.status, outcome: m.outcome || null, resolvedAt: m.resolvedAt || '', result };
  }).sort((a, b) => (b.at || '').localeCompare(a.at || ''));
  return {
    user: user.nick ? { nick: user.nick, provider: user.provider || null, since: user.createdAt || '' } : null,
    stats: stats(preds), preds,
  };
}

// ── 랭킹 ─────────────────────────────────────────────────────
const KST = 9 * 3600e3;
function periodRange(period) {
  const now = new Date(Date.now() + KST);                       // 한국 시각을 UTC 필드로
  const day0 = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - KST;
  if (period === 'month') return [Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1) - KST, Infinity];
  const monday = day0 - ((now.getUTCDay() + 6) % 7) * 864e5;    // 월요일 0시(한국)
  if (period === 'lastweek') return [monday - 7 * 864e5, monday];
  return [monday, Infinity];
}

const rankCache = {};
async function ranking(period) {
  const hit = rankCache[period];
  if (hit && Date.now() - hit.at < 60e3) return hit.rows;
  const [from, to] = periodRange(period);
  const resolved = {};
  (await markets()).forEach((m) => {
    if (m.status !== 'resolved') return;
    const t = m.resolvedAt ? Date.parse(m.resolvedAt) : Date.now();
    if (t >= from && t < to) resolved[m.id] = m;
  });
  const [uids] = await kv([['SMEMBERS', 'users:predicted']]);
  const list = uids || [];
  const data = list.length ? await kv(list.flatMap((u) => [['HGET', `user:${u}`, 'nick'], ['HGETALL', `pred:${u}`]])) : [];
  const rows = list.map((uid, i) => {
    let score = 0, wins = 0, count = 0, best = 0;
    Object.entries(hpairs(data[2 * i + 1])).forEach(([id, v]) => {
      const m = resolved[id];
      if (!m) return;
      const p = JSON.parse(v);
      const b = p.p == null ? 50 : p.p;
      const odds = p.c === 'yes' ? b : 100 - b;
      count++;
      if (p.c === m.outcome) { const pts = Math.round(100 - odds); score += pts; wins++; best = Math.max(best, pts); }
    });
    return { uid, nick: data[2 * i] || '예측러', score, wins, count, best };
  }).filter((r) => r.count > 0).sort((a, b) => b.score - a.score || b.wins - a.wins || a.count - b.count);
  rows.forEach((r, i) => { r.rank = i && r.score === rows[i - 1].score && r.wins === rows[i - 1].wins ? rows[i - 1].rank : i + 1; });
  rankCache[period] = { at: Date.now(), rows };
  return rows;
}

// 예시 순위 (2026-10-21, 사용자 요청: 데모 화면이 비어 보이지 않게).
// 실제 기록이 하나도 없을 때만 내보내고 화면에 '예시'로 표시한다. 실제 사용자가 한 명이라도 생기면
// 자동으로 사라진다 — 가짜 사용자와 실제 사용자가 섞여 경쟁하거나, 예시가 실제 기록처럼 보이지 않게.
const SAMPLE_NICKS = ['역발상왕', '폴리고수', '금리박사', '코인단타', '롤드컵러버', '여의도개미', '새벽시장', '확률덕후',
  '뉴스중독', '데이터맨', '월가지망생', '야구광', '시그널헌터', '조용한고수', '선거분석가', '퀀트초보', '환율감시자',
  '테크러버', '정치9단', '모닝커피', '분석하는곰', '반대로간다', '숫자읽는밤', '예측노트', '오늘도한표', '느긋한황소',
  '이변수집가', '팩트체커', '주말트레이더', '첫눈기다림'];
function sampleRows(period) {
  const scale = period === 'month' ? 3.4 : period === 'lastweek' ? 0.9 : 1;
  const shift = period === 'month' ? 7 : period === 'lastweek' ? 3 : 0;
  const rows = SAMPLE_NICKS.map((nick, i) => {
    const n = SAMPLE_NICKS[(i + shift) % SAMPLE_NICKS.length];
    const score = Math.round((330 - i * 10.5 - (i % 3) * 3) * scale);
    const count = Math.max(3, Math.round((9 - (i % 5)) * (scale > 2 ? 3 : 1)));
    const wins = Math.max(1, Math.min(count, Math.round(count * (0.75 - i * 0.012))));
    const best = Math.max(10, 88 - i * 3 - (i % 4) * 5);
    return { rank: i + 1, nick: n, score, wins, count, best, me: false, sample: true };
  });
  return rows;
}

const RQ_CATS = ['경제', '코인', '정치·세계', '스포츠', '테크·문화', '생활·연예'];

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!ready()) return res.status(503).json({ error: '예측 저장소가 아직 연결되지 않았습니다.' });
  try {
    let uid = readUid(req);
    if (req.method === 'GET') {
      if (req.query && req.query.view === 'rank') {
        const period = ['week', 'lastweek', 'month'].includes(req.query.period) ? req.query.period : 'week';
        const rows = await ranking(period);
        const mine = uid ? rows.find((r) => r.uid === uid) : null;
        const pub = (r) => ({ rank: r.rank, nick: r.nick, score: r.score, wins: r.wins, count: r.count, best: r.best, me: r.uid === uid });
        if (!rows.length) return res.json({ period, rows: sampleRows(period), me: null, players: 0, sample: true });
        return res.json({ period, rows: rows.slice(0, 30).map(pub), me: mine ? pub(mine) : null, players: rows.length });
      }
      if (!uid) return res.json({ user: null, stats: stats([]), preds: [] });
      return res.json(await profile(uid));
    }
    if (req.method !== 'POST') return res.status(405).end();
    const b = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});

    if (b.action === 'logout') { clearUid(res); return res.json({ ok: true }); }

    if (b.action === 'nick') {
      if (!uid) return res.status(400).json({ error: '먼저 예측을 하나 해 주세요.' });
      const nick = String(b.nick || '').trim();
      if (!NICK_RE.test(nick)) return res.status(400).json({ error: '닉네임은 2~12자 (한글·영문·숫자)로 해 주세요.' });
      await kv([['HSET', `user:${uid}`, 'nick', nick]]);
      return res.json(await profile(uid));
    }

    if (b.action === 'predict') {
      const id = String(b.id || '');
      const choice = b.choice;
      if (!/^(\d{1,12}|r[a-z0-9]{6,20})$/.test(id) || (choice !== 'yes' && choice !== 'no')) return res.status(400).json({ error: 'bad request' });
      const m = (await markets(id.startsWith('r'))).find((x) => x.id === id);   // 독자 질문은 지금 비율로
      if (!m || m.status !== 'live') return res.status(409).json({ error: '예측이 마감된 질문이에요.' });
      const [provider] = uid ? await kv([['HGET', `user:${uid}`, 'provider']]) : [null];
      if (!provider) return res.status(401).json({ error: '로그인하면 예측할 수 있어요.', login: true });
      const now = new Date().toISOString();
      const [first] = await kv([
        ['HSETNX', `pred:${uid}`, id, JSON.stringify({ c: choice, at: now, p: m.kind === 'reader' ? m.odds : m.market, q: m.q })],
        ['SADD', 'users:predicted', uid],
      ]);
      if (first !== 1) return res.status(409).json({ error: '이미 예측한 질문이에요.' });
      const [, counts] = await kv([['HINCRBY', `poll:pm-${id}`, choice, 1], ['HGETALL', `poll:pm-${id}`]]);
      const c = hpairs(counts);
      return res.json({ ok: true, readers: { yes: Number(c.yes) || 0, no: Number(c.no) || 0 } });
    }
    if (b.action === 'propose') {
      const [u] = uid ? await kv([['HGETALL', `user:${uid}`]]) : [null];
      const user = hpairs(u);
      if (!user.provider) return res.status(401).json({ error: '로그인하면 질문을 제안할 수 있어요.', login: true });
      const q = String(b.q || '').trim().replace(/\s+/g, ' ');
      const cat = RQ_CATS.includes(b.cat) ? b.cat : '생활·연예';
      const how = String(b.how || '').trim().slice(0, 60);
      const closes = Date.parse(b.closesAt);
      if (q.length < 8 || q.length > 80 || !/[?？]$/.test(q)) return res.status(400).json({ error: '질문은 8~80자, 물음표로 끝나게 써 주세요.' });
      if (!(closes > Date.now() + 2 * 3600e3 && closes < Date.now() + 90 * 864e5)) return res.status(400).json({ error: '마감은 지금부터 2시간 뒤 ~ 90일 안으로 정해 주세요.' });
      if (how.length < 2) return res.status(400).json({ error: '결과를 어디서 확인하는지 적어 주세요.' });
      const day = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
      const [n] = await kv([['INCR', `rq:limit:${uid}:${day}`], ['EXPIRE', `rq:limit:${uid}:${day}`, 86400]]);
      if (n > 3) return res.status(429).json({ error: '질문 제안은 하루 3개까지예요.' });
      const id = 'r' + Date.now().toString(36) + crypto.randomBytes(2).toString('hex');
      const now = new Date().toISOString();
      await kv([
        ['HSET', `rq:${id}`, 'q', q, 'cat', cat, 'closesAt', new Date(closes).toISOString(), 'how', how,
          'by', uid, 'byNick', user.nick || '', 'status', 'pending', 'createdAt', now],
        ['ZADD', 'rq:pending', Date.now(), id],
      ]);
      return res.json({ ok: true, id });
    }
    return res.status(400).json({ error: 'bad action' });
  } catch (e) {
    return res.status(500).json({ error: '처리 중 오류가 났습니다.' });
  }
};
