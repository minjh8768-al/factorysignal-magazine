// 관리자 페이지(/admin.html) API. 2026-10-20 — 현황 · 승인 대기 초안 확인·수정·발행·보류.
// 모든 요청은 헤더 x-admin-key 가 MAGAZINE_ADMIN_SECRET 과 같아야 한다.
//
//   GET  ?view=stats                 최근 14일 방문, 오늘 많이 본 기사, 구독자·투표 수
//   GET  ?view=polls                 투표별 질문·기사·예/아니오 수 (많이 참여한 순)
//   GET  ?view=drafts                승인 대기 초안 목록 (Upstash draft:*)
//   GET  ?view=draft&slug=           초안 하나 (편집용 필드 + 미리보기 HTML)
//   GET  ?view=photos&q=             카드 사진 후보 (위키미디어 커먼즈, 상업 이용 가능한 라이선스만)
//   POST {action:'save', slug, title, description, poll, body}   초안 수정
//   POST {action:'publish', slug}    수정된 HTML을 담아 GitHub publish-draft 워크플로 실행 → 1~3분 뒤 반영
//   (초안은 승인 대기 화면을 열 때 daily 워크플로의 결과물에서 자동으로 가져온다 — syncDrafts)
//   POST {action:'skip', slug}       초안 보류(삭제)
//
// 환경변수: MAGAZINE_ADMIN_SECRET(비밀번호), GITHUB_DISPATCH_TOKEN(이 저장소 Actions 쓰기), KV_REST_API_*
const crypto = require('crypto');
const topics = require('./_odds-topics.json');
const { DATA } = require('./_lib');

const REPO = 'minjh8768-al/factorysignal-magazine';
const URL_ = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
const SECRET = process.env.MAGAZINE_ADMIN_SECRET || '';
const GH = (process.env.GITHUB_DISPATCH_TOKEN || '').trim();   // 붙여넣을 때 섞인 공백·줄바꿈 제거
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

// 카드 사진 후보 — tools/commons.py 와 같은 라이선스 기준(CC0·퍼블릭 도메인·CC BY·CC BY-SA, NC·ND 제외).
// 고르는 건 사람이 눈으로 하므로 연도·인물 필터는 두지 않는다. (2026-10-21)
const LIC_OK = /^(cc0|public domain|pd|cc by(-sa)? [\d.]+( [a-z]{2,3})?|kogl type 1)/i;
const LIC_BAD = /\b(nc|nd)\b/i;
const strip = (s) => String(s || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();

async function photoCandidates(q) {
  const params = new URLSearchParams({
    action: 'query', format: 'json', generator: 'search', gsrsearch: `${q} filetype:bitmap`, gsrnamespace: '6',
    gsrlimit: '30', prop: 'imageinfo', iiprop: 'url|extmetadata|size', iiurlwidth: '960', origin: '*',
  });
  const r = await fetch(`https://commons.wikimedia.org/w/api.php?${params}`, {
    headers: { 'User-Agent': 'FactoryMagazine/1.0 (https://factorysignal-magazine.vercel.app)' }, signal: AbortSignal.timeout(10000),
  });
  const pages = Object.values(((await r.json()).query || {}).pages || {}).sort((a, b) => (a.index || 99) - (b.index || 99));
  const out = [];
  for (const p of pages) {
    const ii = (p.imageinfo || [])[0] || {};
    const m = ii.extmetadata || {};
    const lic = strip(m.LicenseShortName && m.LicenseShortName.value);
    if (!LIC_OK.test(lic) || LIC_BAD.test(lic) || (ii.width || 0) < 600 || (ii.height && ii.width / ii.height < 0.9)) continue;
    // 풍자화·만화·로고·포스터·머그샷·흉내 내는 사람 등은 기사 대표 사진으로 쓰지 않는다 (중립성).
    if (/caricature|cartoon|satire|parody|meme|impersonat|look-?alike|mug ?shot|logo|poster|emblem|mascot|sticker|banner|wax|tweet|screenshot|illustration|drawing|painting/i.test(String(p.title || ''))) continue;
    const date = strip(m.DateTimeOriginal && m.DateTimeOriginal.value).match(/(19|20)\d\d/);
    out.push({ url: ii.thumburl || ii.url, by: strip(m.Artist && m.Artist.value).slice(0, 60) || 'Wikimedia Commons',
      license: lic, src: ii.descriptionurl || '', title: String(p.title || '').replace(/^File:/, ''), year: date ? date[0] : '' });
    if (out.length >= 12) break;
  }
  return out;
}

function applyPhoto(html, photo) {
  html = html.replace(/<meta name="fs:photo(?:_by|_license|_src)?" content="[^"]*" \/>\n?/g, '');
  if (!photo || !/^https:\/\//.test(photo.url || '')) return html;     // '사진 없이'
  const tags = [`<meta name="fs:photo" content="${esc(photo.url)}" />`];
  if (photo.by) tags.push(`<meta name="fs:photo_by" content="${esc(String(photo.by).slice(0, 80))}" />`);
  if (photo.license) tags.push(`<meta name="fs:photo_license" content="${esc(String(photo.license).slice(0, 40))}" />`);
  if (photo.src && /^https:\/\//.test(photo.src)) tags.push(`<meta name="fs:photo_src" content="${esc(photo.src)}" />`);
  return html.replace('<link rel="stylesheet"', `${tags.join('\n')}\n<link rel="stylesheet"`);
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
  if (f.photo !== undefined) html = applyPhoto(html, f.photo);   // null = 사진 없이
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

let lastSyncError = '';
async function syncDrafts() {
  lastSyncError = '';
  if (!GH) { lastSyncError = 'GITHUB_DISPATCH_TOKEN 없음'; return; }
  const r = await gh('/actions/artifacts?per_page=30');
  if (!r.ok) { lastSyncError = `결과물 목록 조회 실패 (${r.status})`; return; }
  const weekAgo = Date.now() - 7 * 864e5;
  const fresh = ((await r.json()).artifacts || [])
    .filter((a) => /^drafts-\d+$/.test(a.name) && !a.expired && Date.parse(a.created_at) > weekAgo);
  if (!fresh.length) return;
  const seen = await kv(fresh.map((a) => ['SISMEMBER', 'imported-artifacts', String(a.id)]));
  for (const [i, a] of fresh.entries()) {
    if (Number(seen[i]) === 1) continue;
    // GitHub은 302로 저장소(블롭) 주소를 넘겨준다. 그 주소는 서명이 붙어 있어 인증 헤더가 필요 없고,
    // 헤더가 따라가면 오히려 거절된다 — 그래서 넘겨받은 주소를 헤더 없이 직접 연다. (2026-10-21)
    const hop = await gh(`/actions/artifacts/${a.id}/zip`, { redirect: 'manual' });
    const loc = hop.headers.get('location');
    const z = loc ? await fetch(loc) : hop;
    if (!z.ok) { lastSyncError = `결과물 ${a.name} 내려받기 실패 (${hop.status}/${z.status})`; continue; }
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
    if (r.slug.startsWith('pm-r')) {                     // 독자 질문
      const [q] = await kv([['HMGET', `rq:${r.slug.slice(3)}`, 'q', 'cat', 'status']]);
      Object.assign(r, { kind: 'odds', question: (q && q[0]) || r.slug, title: `독자 질문${q && q[2] === 'resolved' ? ' · 결과 확정' : ''}`, category: (q && q[1]) || '' });
      return;
    }
    if (r.slug.startsWith('pm-')) {
      const m = (DATA.markets || []).find((x) => `pm-${x.id}` === r.slug);
      Object.assign(r, { kind: 'odds', question: m ? m.q : r.slug, title: m && m.status === 'resolved' ? `예측 질문 · 결과 ${m.outcome === 'yes' ? '예' : '아니오'}` : '예측 질문', category: m ? m.cat : '' });
      return;
    }
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

// ── 독자 질문 관리 (2026-10-21) ─────────────────────────────────
// 제안(rq:pending) → 승인(rq:live) → 마감 뒤 결과 확정(rq:resolved) 또는 무효(취소, 점수 없음).
const RQ_ID = /^r[a-z0-9]{6,20}$/;
async function rqList(ids) {
  if (!ids.length) return [];
  const rows = await kv(ids.flatMap((id) => [['HGETALL', `rq:${id}`], ['HGETALL', `poll:pm-${id}`]]));
  const pairs = (a) => { const o = {}; for (let i = 0; i + 1 < (a || []).length; i += 2) o[a[i]] = a[i + 1]; return o; };
  return ids.map((id, i) => {
    const r = pairs(rows[2 * i]), c = pairs(rows[2 * i + 1]);
    return { id, ...r, yes: Number(c.yes) || 0, no: Number(c.no) || 0 };
  });
}

async function proposals() {
  const [pending, live] = await kv([['ZRANGE', 'rq:pending', 0, 99], ['ZRANGE', 'rq:live', 0, -1]]);
  const liveRows = await rqList(live || []);
  const now = Date.now();
  return {
    pending: await rqList(pending || []),
    awaiting: liveRows.filter((r) => Date.parse(r.closesAt) <= now),   // 마감됨 — 결과를 정해 주세요
    live: liveRows.filter((r) => Date.parse(r.closesAt) > now),
  };
}

async function rqAction(b) {
  const id = String(b.id || '');
  if (!RQ_ID.test(id)) throw new Error('bad id');
  if (b.action === 'rq_approve') {
    const sets = [];
    const q = String(b.q || '').trim();
    if (q.length >= 8 && q.length <= 80) sets.push('q', q);
    const closes = Date.parse(b.closesAt);
    if (closes > Date.now()) sets.push('closesAt', new Date(closes).toISOString());
    await kv([
      ...(sets.length ? [['HSET', `rq:${id}`, ...sets]] : []),
      ['HSET', `rq:${id}`, 'status', 'live', 'approvedAt', new Date().toISOString()],
      ['ZREM', 'rq:pending', id], ['ZADD', 'rq:live', Date.now(), id],
    ]);
  } else if (b.action === 'rq_reject') {
    await kv([['HSET', `rq:${id}`, 'status', 'rejected'], ['ZREM', 'rq:pending', id]]);
  } else if (b.action === 'rq_resolve') {
    const outcome = b.outcome;
    if (outcome === 'void') {
      await kv([['HSET', `rq:${id}`, 'status', 'void'], ['ZREM', 'rq:live', id]]);
    } else if (outcome === 'yes' || outcome === 'no') {
      const [c] = await kv([['HGETALL', `poll:pm-${id}`]]);
      const o = {}; for (let i = 0; i + 1 < (c || []).length; i += 2) o[c[i]] = Number(c[i + 1]) || 0;
      const n = (o.yes || 0) + (o.no || 0);
      const final = n ? Math.round(((o.yes || 0) / n) * 1000) / 10 : 50;
      const now = new Date().toISOString();
      await kv([
        ['HSET', `rq:${id}`, 'status', 'resolved', 'outcome', outcome, 'final', final, 'resolvedAt', now],
        ['ZREM', 'rq:live', id], ['ZADD', 'rq:resolved', Date.now(), id],
      ]);
    } else throw new Error('bad outcome');
  } else throw new Error('bad action');
  return { ok: true };
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
      if (view === 'proposals') return res.json(await proposals());
      if (view === 'drafts') {
        try { await syncDrafts(); } catch (e) { lastSyncError = `가져오기 오류: ${e.message}`; }
        const keys = await scan('draft:*');
        const vals = keys.length ? await kv(keys.map((k) => ['GET', k])) : [];
        const list = vals.map((v, i) => {
          const d = JSON.parse(v || '{}');
          if (d.status === 'published') return null;      // 발행 처리 중·완료 — 목록에서 뺀다
          const f = fields(d.html || '');
          return { slug: keys[i].slice(6), date: d.date, title: f.title, category: f.category, photo: f.photo, poll: f.poll };
        }).filter(Boolean).sort((a, b) => (b.date || '').localeCompare(a.date || ''));
        return res.json({ drafts: list, syncError: lastSyncError });
      }
      if (view === 'photos') {
        const q = String(req.query.q || '').trim().slice(0, 80);
        if (q.length < 2) return res.json({ photos: [] });
        return res.json({ photos: await photoCandidates(q) });
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
    if (String(b.action || '').startsWith('rq_')) return res.json(await rqAction(b));
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
