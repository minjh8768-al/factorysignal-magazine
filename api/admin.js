// 관리자 페이지(/admin.html) API. 2026-10-20 — 현황 · 승인 대기 초안 확인·수정·발행·보류.
// 모든 요청은 헤더 x-admin-key 가 MAGAZINE_ADMIN_SECRET 과 같아야 한다.
//
//   GET  ?view=stats                 최근 14일 방문, 오늘 많이 본 기사, 구독자·투표 수
//   GET  ?view=drafts                승인 대기 초안 목록 (Upstash draft:*)
//   GET  ?view=draft&slug=           초안 하나 (편집용 필드 + 미리보기 HTML)
//   POST {action:'save', slug, title, description, poll, body}   초안 수정
//   POST {action:'publish', slug}    GitHub publish-draft 워크플로 실행 → 1~3분 뒤 사이트 반영
//   POST {action:'skip', slug}       초안 보류(삭제)
//
// 환경변수: MAGAZINE_ADMIN_SECRET(비밀번호), GITHUB_DISPATCH_TOKEN(이 저장소 Actions 쓰기), KV_REST_API_*
const crypto = require('crypto');

const REPO = 'minjh8768-al/factorysignal-magazine';
const URL_ = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
const SECRET = process.env.MAGAZINE_ADMIN_SECRET || '';
const GH = process.env.GITHUB_DISPATCH_TOKEN;
const SLUG_RE = /^[a-z0-9][a-z0-9-]{2,119}$/;
// 본문 편집에서 허용하는 태그 (기사 생성 규칙과 같다). 나머지 태그·속성은 지운다.
const ALLOWED = new Set(['p', 'h2', 'h3', 'blockquote', 'ul', 'ol', 'li', 'strong', 'em', 'a', 'br']);

async function kv(commands) {
  const r = await fetch(`${URL_}/pipeline`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(commands),
  });
  if (!r.ok) throw new Error(`redis ${r.status}`);
  return (await r.json()).map((x) => x.result);
}

async function scan(pattern) {
  let cursor = '0';
  const keys = [];
  do {
    const [res] = await kv([['SCAN', cursor, 'MATCH', pattern, 'COUNT', 200]]);
    cursor = res[0];
    keys.push(...res[1]);
  } while (cursor !== '0' && keys.length < 5000);
  return keys;
}

function same(a, b) {
  const x = Buffer.from(String(a)), y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const unesc = (s) => String(s).replace(/&quot;/g, '"').replace(/&#x27;|&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const meta = (h, n) => { const m = h.match(new RegExp(`<meta name="${n}" content="([^"]*)"`)); return m ? unesc(m[1]) : ''; };

function sanitize(body) {
  return String(body)
    .replace(/<(script|style|iframe|img|svg|div|span)[^>]*>[\s\S]*?<\/\1>/gi, '')
    .replace(/<\/?([a-z0-9]+)([^>]*)>/gi, (tag, name, attrs) => {
      name = name.toLowerCase();
      if (!ALLOWED.has(name)) return '';
      if (tag.startsWith('</')) return `</${name}>`;
      if (name === 'a') {
        const href = (attrs.match(/href="(https?:\/\/[^"]+)"/i) || [])[1];
        return href ? `<a href="${href}" target="_blank" rel="noopener">` : '<a>';
      }
      return `<${name}>`;
    });
}

// 기사 HTML에서 편집할 부분 — 본문은 '원본 영상' 안내 다음부터 면책 문구 전까지.
const BODY_RE = /(<p class="source-note">[\s\S]*?<\/p>\s*)([\s\S]*?)(\s*<div class="disclaimer">)/;

function fields(html) {
  const title = (html.match(/<h1>([\s\S]*?)<\/h1>/) || [])[1] || '';
  return {
    title: unesc(title), description: meta(html, 'description'), poll: meta(html, 'fs:poll'),
    category: meta(html, 'fs:category'), eyebrow: meta(html, 'fs:eyebrow'), photo: meta(html, 'fs:photo'),
    photoBy: meta(html, 'fs:photo_by'), photoLicense: meta(html, 'fs:photo_license'), video: meta(html, 'fs:video'),
    body: (html.match(BODY_RE) || [])[2] || '',
  };
}

function applyEdits(html, f) {
  const title = String(f.title || '').trim().slice(0, 140);
  const desc = String(f.description || '').trim().slice(0, 240);
  const poll = String(f.poll || '').trim().slice(0, 80);
  if (title) {
    html = html.replace(/<title>[\s\S]*?( — Factory Magazine)?<\/title>/, `<title>${esc(title)} — Factory Magazine</title>`)
      .replace(/<h1>[\s\S]*?<\/h1>/, `<h1>${esc(title)}</h1>`);
  }
  if (desc) html = html.replace(/<meta name="description" content="[^"]*" \/>/, `<meta name="description" content="${esc(desc)}" />`);
  html = html.replace(/<meta name="fs:poll" content="[^"]*" \/>\n?/, '');
  if (poll.length >= 8 && poll.endsWith('?')) {
    html = html.replace('<link rel="stylesheet"', `<meta name="fs:poll" content="${esc(poll)}" />\n<link rel="stylesheet"`);
  }
  if (typeof f.body === 'string' && f.body.trim()) {
    html = html.replace(BODY_RE, (m, a, _b, c) => `${a}${sanitize(f.body)}${c}`);
  }
  return html;
}

async function stats() {
  const days = [];
  for (let i = 13; i >= 0; i--) days.push(new Date(Date.now() + 9 * 3600e3 - i * 864e5).toISOString().slice(0, 10));
  const res = await kv([
    ...days.map((d) => ['GET', `pv:${d}`]), ...days.map((d) => ['PFCOUNT', `uv:${d}`]),
    ['ZREVRANGE', `top:${days[13]}`, 0, 9, 'WITHSCORES'], ['ZREVRANGE', `top:${days[12]}`, 0, 9, 'WITHSCORES'],
    ['SCARD', 'subscribers'],
  ]);
  const pv = res.slice(0, 14).map(Number), uv = res.slice(14, 28).map(Number);
  const pairs = (a) => { const o = []; for (let i = 0; i + 1 < (a || []).length; i += 2) o.push({ slug: a[i], views: Number(a[i + 1]) }); return o; };
  // 구독자 신규(오늘·이번 주)와 투표 합계 — 규모가 작을 때를 전제로 한 단순 집계.
  const emails = (await kv([['SMEMBERS', 'subscribers']]))[0] || [];
  const consent = emails.length ? await kv(emails.map((e) => ['HGET', `sub:${e}`, 'consentedAt'])) : [];
  const kst = consent.map((c) => (c ? new Date(Date.parse(c) + 9 * 3600e3).toISOString().slice(0, 10) : ''));
  const polls = await scan('poll:*');
  const pollVals = polls.length ? await kv(polls.map((k) => ['HGETALL', k])) : [];
  let votes = 0;
  pollVals.forEach((a) => { for (let i = 1; i < (a || []).length; i += 2) votes += Number(a[i]) || 0; });
  return {
    days, pv, uv,
    topToday: pairs(res[28]), topYesterday: pairs(res[29]),
    subscribers: Number(res[30]) || 0,
    newSubsToday: kst.filter((d) => d === days[13]).length,
    newSubsWeek: kst.filter((d) => d >= days[7]).length,
    votes, polls: polls.length,
  };
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!SECRET || !URL_ || !TOKEN) return res.status(503).json({ error: '관리자 설정(비밀번호·저장소)이 없습니다.' });
  if (!same(req.headers['x-admin-key'] || '', SECRET)) return res.status(401).json({ error: '비밀번호가 맞지 않습니다.' });

  try {
    if (req.method === 'GET') {
      const view = req.query.view;
      if (view === 'stats') return res.json(await stats());
      if (view === 'drafts') {
        const keys = await scan('draft:*');
        const vals = keys.length ? await kv(keys.map((k) => ['GET', k])) : [];
        const list = vals.map((v, i) => {
          const d = JSON.parse(v || '{}');
          const f = fields(d.html || '');
          return { slug: keys[i].slice(6), date: d.date, title: f.title, category: f.category, photo: f.photo, poll: f.poll };
        }).sort((a, b) => (b.date || '').localeCompare(a.date || ''));
        return res.json({ drafts: list });
      }
      if (view === 'draft') {
        const slug = String(req.query.slug || '');
        if (!SLUG_RE.test(slug)) return res.status(400).json({ error: 'bad slug' });
        const v = (await kv([['GET', `draft:${slug}`]]))[0];
        if (!v) return res.status(404).json({ error: '초안이 없습니다 (이미 처리됐거나 7일 지남).' });
        const d = JSON.parse(v);
        return res.json({ slug, date: d.date, ...fields(d.html), html: d.html });
      }
      return res.status(400).json({ error: 'bad view' });
    }

    if (req.method !== 'POST') return res.status(405).end();
    const b = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const slug = String(b.slug || '');
    if (!SLUG_RE.test(slug)) return res.status(400).json({ error: 'bad slug' });
    const key = `draft:${slug}`;
    const v = (await kv([['GET', key]]))[0];
    if (!v) return res.status(404).json({ error: '초안이 없습니다 (이미 처리됐거나 7일 지남).' });

    if (b.action === 'save') {
      const d = JSON.parse(v);
      d.html = applyEdits(d.html, b);
      await kv([['SET', key, JSON.stringify(d), 'KEEPTTL']]);
      return res.json({ ok: true, ...fields(d.html) });
    }
    if (b.action === 'skip') {
      await kv([['DEL', key]]);
      return res.json({ ok: true });
    }
    if (b.action === 'publish') {
      if (!GH) return res.status(503).json({ error: 'GITHUB_DISPATCH_TOKEN 이 없습니다.' });
      const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/publish-draft.yml/dispatches`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${GH}`, Accept: 'application/vnd.github+json', 'User-Agent': 'factory-magazine' },
        body: JSON.stringify({ ref: 'main', inputs: { slug } }),
      });
      if (r.status !== 204) return res.status(502).json({ error: `발행 요청 실패 (GitHub ${r.status})` });
      return res.json({ ok: true });
    }
    return res.status(400).json({ error: 'bad action' });
  } catch (e) {
    return res.status(500).json({ error: '처리 중 오류가 났습니다.' });
  }
};

// 테스트용 (네트워크 없이 편집 로직만)
module.exports._test = { fields, applyEdits, sanitize };
