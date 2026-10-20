// 기사 하단 예/아니오 투표.
//   GET  /api/vote?slug=xxx            → { yes, no }
//   POST /api/vote { slug, choice }    → { yes, no, counted }
//
// 저장소는 Vercel에 연결한 Upstash Redis (REST). 연결하면 KV_REST_API_URL /
// KV_REST_API_TOKEN 이 자동으로 들어온다. 이름이 UPSTASH_REDIS_REST_* 인 경우도 받는다.
// 로그인 없는 투표라 같은 사람이 여러 번 누르는 것을 IP 해시로 30일간 막는다
// (브라우저 localStorage는 화면 표시용일 뿐 막는 장치가 아니다). IP 원문은 저장하지 않는다.
const crypto = require('crypto');

const URL_ = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
const SLUG_RE = /^[a-z0-9][a-z0-9-]{2,119}$/;
const DEDUPE_SECONDS = 30 * 24 * 60 * 60;

async function redis(commands) {
  const r = await fetch(`${URL_}/pipeline`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(commands),
  });
  if (!r.ok) throw new Error(`redis ${r.status}`);
  return (await r.json()).map((x) => x.result);
}

function counts(hgetall) {
  // Upstash REST의 HGETALL은 [field, value, field, value, ...] 배열을 돌려준다.
  const out = { yes: 0, no: 0 };
  for (let i = 0; i + 1 < (hgetall || []).length; i += 2) {
    if (hgetall[i] in out) out[hgetall[i]] = Number(hgetall[i + 1]) || 0;
  }
  return out;
}

function voterKey(req, slug) {
  const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
  const hash = crypto.createHash('sha256').update(`${slug}|${ip}|factory-magazine-poll`).digest('hex');
  return `voted:${slug}:${hash.slice(0, 32)}`;
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!URL_ || !TOKEN) return res.status(503).json({ error: '투표 저장소가 아직 연결되지 않았습니다.' });

  try {
    if (req.method === 'GET') {
      const slug = String(req.query.slug || '');
      if (!SLUG_RE.test(slug)) return res.status(400).json({ error: 'bad slug' });
      const [all] = await redis([['HGETALL', `poll:${slug}`]]);
      return res.json(counts(all));
    }

    if (req.method === 'POST') {
      const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
      const slug = String(body.slug || '');
      const choice = body.choice;
      if (!SLUG_RE.test(slug) || (choice !== 'yes' && choice !== 'no')) {
        return res.status(400).json({ error: 'bad request' });
      }
      const [first] = await redis([['SET', voterKey(req, slug), choice, 'NX', 'EX', DEDUPE_SECONDS]]);
      const counted = first === 'OK';
      const cmds = counted
        ? [['HINCRBY', `poll:${slug}`, choice, 1], ['HGETALL', `poll:${slug}`]]
        : [['HGETALL', `poll:${slug}`]];
      const results = await redis(cmds);
      return res.json({ ...counts(results[results.length - 1]), counted });
    }

    return res.status(405).json({ error: 'method not allowed' });
  } catch (e) {
    return res.status(500).json({ error: '투표 처리 중 오류가 났습니다.' });
  }
};
