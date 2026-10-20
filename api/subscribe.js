// 뉴스레터 구독 신청.
//   POST /api/subscribe { email, letters: ['daily','weekly'], consent: true }
//   GET  /api/subscribe?format=csv  (헤더 x-admin-secret = MAGAZINE_ADMIN_SECRET) → 명단 CSV
//
// 발송 서비스(스티비 등)를 정하기 전에도 신청을 받기 위해 투표와 같은 Upstash Redis에
// 모아 둔다. 발송 서비스가 생기면 CSV로 내려받아 옮긴다. 수집 항목은 이메일 하나뿐이고,
// 동의 시각을 함께 남긴다(개인정보 수집·이용 동의 증빙).
const crypto = require('crypto');

const URL_ = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
const ADMIN = process.env.MAGAZINE_ADMIN_SECRET;
const LETTERS = new Set(['daily', 'weekly']);
const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}$/;

async function redis(commands) {
  const r = await fetch(`${URL_}/pipeline`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(commands),
  });
  if (!r.ok) throw new Error(`redis ${r.status}`);
  return (await r.json()).map((x) => x.result);
}

function csvCell(v) {
  const s = String(v ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!URL_ || !TOKEN) return res.status(503).json({ error: '구독 저장소가 아직 연결되지 않았습니다.' });

  try {
    if (req.method === 'GET') {
      if (!ADMIN || req.headers['x-admin-secret'] !== ADMIN) return res.status(404).end();
      const [emails] = await redis([['SMEMBERS', 'subscribers']]);
      const rows = emails.length ? await redis(emails.map((e) => ['HGETALL', `sub:${e}`])) : [];
      const lines = ['email,letters,consented_at,source'];
      emails.forEach((e, i) => {
        const h = {};
        for (let k = 0; k + 1 < (rows[i] || []).length; k += 2) h[rows[i][k]] = rows[i][k + 1];
        lines.push([e, h.letters, h.consentedAt, h.source].map(csvCell).join(','));
      });
      res.setHeader('Content-Type', 'text/csv; charset=utf-8');
      return res.send('﻿' + lines.join('\n'));
    }

    if (req.method !== 'POST') return res.status(405).json({ error: 'method not allowed' });

    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const email = String(body.email || '').trim().toLowerCase();
    const letters = (Array.isArray(body.letters) ? body.letters : []).filter((l) => LETTERS.has(l));
    if (!EMAIL_RE.test(email)) return res.status(400).json({ error: '이메일 주소를 확인해 주세요.' });
    if (!letters.length) return res.status(400).json({ error: '받아볼 뉴스레터를 하나 이상 골라 주세요.' });
    if (body.consent !== true) return res.status(400).json({ error: '개인정보 수집·이용에 동의해 주세요.' });

    // 같은 IP의 연속 신청을 10초에 한 번으로 제한 (자동 대량 등록 방지).
    const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
    const ipKey = `subrate:${crypto.createHash('sha256').update(ip).digest('hex').slice(0, 24)}`;
    const [ok] = await redis([['SET', ipKey, '1', 'NX', 'EX', 10]]);
    if (ok !== 'OK') return res.status(429).json({ error: '잠시 후 다시 시도해 주세요.' });

    await redis([
      ['SADD', 'subscribers', email],
      ['HSET', `sub:${email}`, 'letters', letters.join('|'),
        'consentedAt', new Date().toISOString(), 'source', String(body.source || 'subscribe-page').slice(0, 40)],
    ]);
    return res.json({ success: true });
  } catch (e) {
    return res.status(500).json({ error: '구독 처리 중 오류가 났습니다.' });
  }
};
