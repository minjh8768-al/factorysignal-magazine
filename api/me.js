// 내 예측과 프로필 (2026-10-20).
//   GET  /api/me                              → { user, stats, preds }  (예측한 적 없으면 user: null)
//   POST /api/me { action:'predict', id, choice:'yes'|'no' }   가상 예측 (질문당 한 번, 바꿀 수 없음)
//   POST /api/me { action:'nick', nick }      닉네임 바꾸기
//   POST /api/me { action:'logout' }
// 돈·포인트는 없다. 예/아니오를 골라 두고 결과가 나면 맞혔는지만 센다.
// 저장(Upstash): user:{uid} 해시(nick, createdAt, provider), pred:{uid} 해시(질문id → {c, at, p}),
//               poll:pm-{id} 해시(yes/no 독자 수).
const { kv, hpairs, markets, readUid, setUid, clearUid, newUid, ready } = require('./_lib');

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
    const pickedOdds = p.c === 'yes' ? p.p : Math.round((100 - p.p) * 10) / 10;
    const result = m.status === 'resolved' ? (m.outcome === p.c ? 'win' : 'lose') : m.status === 'gone' ? 'unknown' : 'open';
    return { id, q: m.q, cat: m.cat || '', choice: p.c, at: p.at, pickedOdds, market: m.market ?? null,
      status: m.status, outcome: m.outcome || null, resolvedAt: m.resolvedAt || '', result };
  }).sort((a, b) => (b.at || '').localeCompare(a.at || ''));
  return {
    user: user.nick ? { nick: user.nick, provider: user.provider || null, since: user.createdAt || '' } : null,
    stats: stats(preds), preds,
  };
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!ready()) return res.status(503).json({ error: '예측 저장소가 아직 연결되지 않았습니다.' });
  try {
    let uid = readUid(req);
    if (req.method === 'GET') {
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
      if (!/^\d{1,12}$/.test(id) || (choice !== 'yes' && choice !== 'no')) return res.status(400).json({ error: 'bad request' });
      const m = (await markets()).find((x) => x.id === id);
      if (!m || m.status !== 'live') return res.status(409).json({ error: '예측이 마감된 질문이에요.' });
      if (!uid) {
        uid = newUid();
        setUid(res, uid);
      }
      const now = new Date().toISOString();
      const [isNew, first] = await kv([
        ['HSETNX', `user:${uid}`, 'createdAt', now],
        ['HSETNX', `pred:${uid}`, id, JSON.stringify({ c: choice, at: now, p: m.market, q: m.q })],
      ]);
      if (isNew === 1) await kv([['HSETNX', `user:${uid}`, 'nick', `예측러${String(parseInt(uid.slice(0, 6), 16) % 10000).padStart(4, '0')}`]]);
      if (first !== 1) return res.status(409).json({ error: '이미 예측한 질문이에요.' });
      const [, counts] = await kv([['HINCRBY', `poll:pm-${id}`, choice, 1], ['HGETALL', `poll:pm-${id}`]]);
      const c = hpairs(counts);
      return res.json({ ok: true, readers: { yes: Number(c.yes) || 0, no: Number(c.no) || 0 } });
    }
    return res.status(400).json({ error: 'bad action' });
  } catch (e) {
    return res.status(500).json({ error: '처리 중 오류가 났습니다.' });
  }
};
