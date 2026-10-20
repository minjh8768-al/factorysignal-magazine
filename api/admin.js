// 관리자 페이지(/admin.html) API. 2026-10-20 — 현황 · 승인 대기 초안 확인·수정·발행·보류.
// 모든 요청은 헤더 x-admin-key 가 MAGAZINE_ADMIN_SECRET 과 같아야 한다.
//
//   GET  ?view=stats                 최근 14일 방문, 오늘 많이 본 기사, 구독자·투표 수
//   GET  ?view=polls                 투표별 질문·기사·예/아니오 수 (많이 참여한 순)
//   GET  ?view=drafts                승인 대기 초안 목록 (Upstash draft:*)
//   GET  ?view=draft&slug=           초안 하나 (편집용 필드 + 미리보기 HTML)
//   POST {action:'save', slug, title, description, poll, body}   초안 수정
//   POST {action:'publish', slug}    수정된 HTML을 담아 GitHub publish-draft 워크플로 실행 → 1~3분 뒤 반영
//   (초안은 승인 대기 화면을 열 때 daily 워크플로의 결과물에서 자동으로 가져온다 — syncDrafts)
//   POST {action:'skip', slug}       초안 보류(삭제)
//
// 환경변수: MAGAZINE_ADMIN_SECRET(비밀번호), GITHUB_DISPATCH_TOKEN(이 저장소 Actions 쓰기), KV_REST_API_*
const crypto = require('crypto');
const topics = require('./_odds-topics.json');

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

// ── 매일 자동 작성 초안 가져오기 ────────────────────────────────────
// daily 워크플로는 초안을 실행 결과물(artifact 'drafts-N')로 남긴다. 승인 대기 화면을 열 때
// GitHub 토큰으로 최근 7일 결과물을 받아 Upstash 에 넣는다 (이미 가져온 것은 건너뜀).
// 이렇게 하면 GitHub 쪽에 저장소 열쇠를 따로 넣지 않아도 된다. (2026-10-20)
const zlib = require('zlib');
const DRAFT_TTL = 7 * 24 * 3600;
const DRAFT_NAME = /^(?:[^/]*\/)?(\d{4}-\d{2}-\d{2})-([a-z0-9][a-z0-9-]{2,119})\.html$/;

function unzip(buf) {
  // 최소한의 zip 읽기: 끝의 중앙 디렉터리에서 항목 목록을 읽고, 저장(0)·deflate(8)만 푼다.
  let eocd = buf.length - 22;
  while (eocd >= 0 && buf.readUInt32LE(eocd) !== 0x06054b50) eocd--;
  if (eocd < 0) return [];
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  const out = [];
  for (let i = 0; i < count; i++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) break;
    const method = buf.readUInt16LE(p + 10), csize = buf.readUInt32LE(p + 20);
    const nlen = buf.readUInt16LE(p + 28), xlen = buf.readUInt16LE(p + 30), clen = buf.readUInt16LE(p + 32);
    const local = buf.readUInt32LE(p + 42);
    const name = buf.slice(p + 46, p + 46 + nlen).toString('utf8');
    const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
    const raw = buf.slice(start, start + csize);
    if (method === 0 || method === 8) out.push({ name, data: method === 8 ? zlib.inflateRawSync(raw) : raw });
    p += 46 + nlen + xlen + clen;
  }
  return out;
}

async function gh(path, opts = {}) {
  return fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...opts,
    headers: { Authorization: `Bearer ${GH}`, Accept: 'application/vnd.github+json', 'User-Agent': 'factory-magazine', ...(opts.headers || {}) },
  });
}

async function syncDrafts() {
  if (!GH) return;
  const r = await gh('/actions/artifacts?per_page=30');
  if (!r.ok) return;
  const weekAgo = Date.now() - 7 * 864e5;
  const fresh = ((await r.json()).artifacts || [])
    .filter((a) => /^drafts-\d+$/.test(a.name) && !a.expired && Date.parse(a.created_at) > weekAgo);
  if (!fresh.length) return;
  const seen = await kv(fresh.map((a) => ['SISMEMBER', 'imported-artifacts', String(a.id)]));
  for (const [i, a] of fresh.entries()) {
    if (Number(seen[i]) === 1) continue;
    const z = await gh(`/actions/artifacts/${a.id}/zip`);   // 저장소 주소로 넘겨줄 때 인증 헤더는 빠진다
    if (!z.ok) continue;
    const cmds = [];
    for (const f of unzip(Buffer.from(await z.arrayBuffer()))) {
      const m = f.name.match(DRAFT_NAME);
      if (!m) continue;
      // 이미 발행했거나 보류한 초안을 되살리지 않게 NX(없을 때만)로 넣는다.
      cmds.push(['SET', `draft:${m[2]}`, JSON.stringify({ date: m[1], html: f.data.toString('utf8') }), 'NX', 'EX', DRAFT_TTL]);
    }
    cmds.push(['SADD', 'imported-artifacts', String(a.id)]);
    await kv(cmds);
  }
}

async function stats() {
  const days = [];
  for (let i = 13; i >= 0; i--) days.push(new Date(Date.now() + 9 * 3600e3 - i * 864e5).toISOString().slice(0, 10));
  const res = await kv([
    ...days.map((d) => ['GET', `pv:${d}`]), ...days.map((d) => ['PFCOUNT', `uv:${d}`]),
    ['ZREVRANGE', `top:${days[13]}`, 0, 9, 'WITHSCORES'], ['ZREVRANGE', `top:${days[12]}`, 0, 9, 'WITHSCORES'],
    ['SCARD', 'subscribers'],
    ...days.map((d) => ['GET', `votes:${d}`]),
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
    votesDaily: res.slice(31, 45).map((v) => Number(v) || 0),
  };
}

// 투표별 집계. 기사 투표의 질문·제목은 저장소에 없으므로 발행된 기사 페이지의 메타에서 읽는다
// (투표가 수십 개 수준일 때를 전제로 한 단순한 방식). odds-* 는 '오늘의 확률' 질문.
async function polls(origin) {
  const keys = await scan('poll:*');
  const vals = keys.length ? await kv(keys.map((k) => ['HGETALL', k])) : [];
  const rows = keys.map((k, i) => {
    const o = { slug: k.slice(5), yes: 0, no: 0 };
    const a = vals[i] || [];
    for (let j = 0; j + 1 < a.length; j += 2) if (a[j] in o) o[a[j]] = Number(a[j + 1]) || 0;
    o.total = o.yes + o.no;
    return o;
  }).sort((a, b) => b.total - a.total).slice(0, 100);
  await Promise.all(rows.map(async (r) => {
    if (r.slug.startsWith('odds-')) {
      const t = topics.find((x) => `odds-${x.key}` === r.slug);
      Object.assign(r, { kind: 'odds', question: t ? t.question : r.slug, title: '오늘의 확률', category: t ? t.group : '' });
      return;
    }
    r.kind = 'article';
    r.url = `/articles/${r.slug}.html`;
    try {
      const h = await (await fetch(origin + r.url, { signal: AbortSignal.timeout(5000) })).text();
      const t = h.match(/<title>([^<]*)<\/title>/);
      r.title = t ? unesc(t[1]).replace(/ — Factory Magazine$/, '') : r.slug;
      r.question = meta(h, 'fs:poll');
      r.category = meta(h, 'fs:category');
      r.date = meta(h, 'fs:date');
    } catch (e) { r.title = r.slug; }
  }));
  return rows;
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!SECRET || !URL_ || !TOKEN) return res.status(503).json({ error: '관리자 설정(비밀번호·저장소)이 없습니다.' });
  if (!same(req.headers['x-admin-key'] || '', SECRET)) return res.status(401).json({ error: '비밀번호가 맞지 않습니다.' });

  try {
    if (req.method === 'GET') {
      const view = req.query.view;
      if (view === 'stats') return res.json(await stats());
      if (view === 'polls') return res.json({ polls: await polls(`https://${req.headers.host}`) });
      if (view === 'drafts') {
        try { await syncDrafts(); } catch (e) { /* 가져오기 실패해도 이미 있는 초안은 보여 준다 */ }
        const keys = await scan('draft:*');
        const vals = keys.length ? await kv(keys.map((k) => ['GET', k])) : [];
        const list = vals.map((v, i) => {
          const d = JSON.parse(v || '{}');
          if (d.status === 'published') return null;      // 발행 처리 중·완료 — 목록에서 뺀다
          const f = fields(d.html || '');
          return { slug: keys[i].slice(6), date: d.date, title: f.title, category: f.category, photo: f.photo, poll: f.poll };
        }).filter(Boolean).sort((a, b) => (b.date || '').localeCompare(a.date || ''));
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
      // 수정이 반영된 기사 HTML 자체를 워크플로 입력으로 넘긴다 (GitHub 쪽에 저장소 열쇠가 없어도 되게).
      const d = JSON.parse(v);
      const html64 = Buffer.from(d.html, 'utf8').toString('base64');
      if (html64.length > 60000) return res.status(413).json({ error: '기사가 너무 길어 발행 요청에 담을 수 없습니다.' });
      const r = await gh('/actions/workflows/publish-draft.yml/dispatches', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ref: 'main', inputs: { slug, date: d.date, html_b64: html64 } }),
      });
      if (r.status !== 204) return res.status(502).json({ error: `발행 요청 실패 (GitHub ${r.status})` });
      d.status = 'published';
      await kv([['SET', key, JSON.stringify(d), 'EX', 86400]]);
      return res.json({ ok: true });
    }
    return res.status(400).json({ error: 'bad action' });
  } catch (e) {
    return res.status(500).json({ error: '처리 중 오류가 났습니다.' });
  }
};

// 테스트용 (네트워크 없이 편집 로직만)
module.exports._test = { fields, applyEdits, sanitize, unzip };
