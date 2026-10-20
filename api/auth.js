// 구글·카카오 로그인 (2026-10-20). 받는 정보는 각 서비스의 회원 번호(sub/id) 하나뿐 —
// 이름·이메일·사진은 요청하지 않는다. 닉네임은 우리 사이트에서 따로 정한다.
//   GET /api/auth?status=1              → { google: bool, kakao: bool }  (키가 설정된 것만 true)
//   GET /api/auth?start=google|kakao    → 로그인 화면으로 이동
//   GET /api/auth?code=...&state=...    → (돌아오는 주소) 계정 연결 후 /articles/profile.html 로
// 손님으로 하던 예측은 로그인한 계정으로 합쳐진다.
//
// 환경변수(Vercel): GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET / KAKAO_REST_API_KEY, KAKAO_CLIENT_SECRET(선택)
// 각 서비스 설정의 '리디렉션 URI'에는 https://<사이트 주소>/api/auth 를 등록한다.
const crypto = require('crypto');
const { kv, hpairs, readUid, setUid, newUid, ready } = require('./_lib');

const G_ID = process.env.GOOGLE_CLIENT_ID, G_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const K_ID = process.env.KAKAO_REST_API_KEY, K_SECRET = process.env.KAKAO_CLIENT_SECRET;
const enabled = { google: Boolean(G_ID && G_SECRET), kakao: Boolean(K_ID) };
const BACK = '/articles/profile.html';

const redirectUri = (req) => `https://${req.headers.host}/api/auth`;
const cookie = (req, name) => (String(req.headers.cookie || '').match(new RegExp(`(?:^|;\\s*)${name}=([\\w-]+)`)) || [])[1];

function go(res, url, extraCookie) {
  if (extraCookie) res.setHeader('Set-Cookie', extraCookie);
  res.statusCode = 302;
  res.setHeader('Location', url);
  res.end();
}

async function form(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(body) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`token ${r.status}`);
  return d;
}

async function accountId(provider, code, req) {
  if (provider === 'google') {
    const t = await form('https://oauth2.googleapis.com/token', {
      code, client_id: G_ID, client_secret: G_SECRET, redirect_uri: redirectUri(req), grant_type: 'authorization_code',
    });
    // id_token을 구글 토큰 주소에서 TLS로 직접 받았으므로 서명 검증 없이 내용을 읽어도 된다 (OIDC 3.1.3.7).
    const payload = JSON.parse(Buffer.from(String(t.id_token).split('.')[1], 'base64url').toString());
    if (payload.aud !== G_ID || !payload.sub) throw new Error('bad id_token');
    return String(payload.sub);
  }
  const body = { grant_type: 'authorization_code', client_id: K_ID, redirect_uri: redirectUri(req), code };
  if (K_SECRET) body.client_secret = K_SECRET;
  const t = await form('https://kauth.kakao.com/oauth/token', body);
  const r = await fetch('https://kapi.kakao.com/v2/user/me', { headers: { Authorization: `Bearer ${t.access_token}` } });
  const me = await r.json();
  if (!r.ok || !me.id) throw new Error('kakao me');
  return String(me.id);
}

// 손님 기록(guest)을 계정 기록(target)으로 합친다. 같은 질문은 계정 쪽이 우선.
async function merge(guest, target) {
  const [preds] = await kv([['HGETALL', `pred:${guest}`]]);
  const p = hpairs(preds);
  const cmds = Object.entries(p).map(([id, v]) => ['HSETNX', `pred:${target}`, id, v]);
  if (cmds.length) await kv(cmds);
  await kv([['DEL', `pred:${guest}`], ['DEL', `user:${guest}`]]);
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  const q = req.query || {};
  if (q.status) return res.json(enabled);
  if (!ready()) return res.status(503).send('로그인 저장소가 아직 연결되지 않았습니다.');

  if (q.start) {
    const provider = q.start;
    if (!enabled[provider]) return go(res, `${BACK}?login=unavailable`);
    const nonce = crypto.randomBytes(16).toString('hex');
    const state = `${provider}.${nonce}`;
    const c = `fm_oauth=${nonce}; Path=/api/auth; Max-Age=600; HttpOnly; Secure; SameSite=Lax`;
    const url = provider === 'google'
      ? `https://accounts.google.com/o/oauth2/v2/auth?${new URLSearchParams({ client_id: G_ID, redirect_uri: redirectUri(req), response_type: 'code', scope: 'openid', state, prompt: 'select_account' })}`
      : `https://kauth.kakao.com/oauth/authorize?${new URLSearchParams({ client_id: K_ID, redirect_uri: redirectUri(req), response_type: 'code', state })}`;
    return go(res, url, c);
  }

  if (q.code && q.state) {
    const [provider, nonce] = String(q.state).split('.');
    if (!enabled[provider] || !nonce || nonce !== cookie(req, 'fm_oauth')) return go(res, `${BACK}?login=failed`);
    try {
      const sub = await accountId(provider, String(q.code), req);
      const key = `acct:${provider}:${crypto.createHash('sha256').update(sub).digest('hex').slice(0, 32)}`;
      const guest = readUid(req);
      let [uid] = await kv([['GET', key]]);
      if (uid) {
        if (guest && guest !== uid) {
          // 손님 기록이 이미 다른 계정에 붙어 있으면 합치지 않는다.
          const [g] = await kv([['HGET', `user:${guest}`, 'provider']]);
          if (!g) await merge(guest, uid);
        }
      } else {
        const [g] = guest ? await kv([['HGET', `user:${guest}`, 'provider']]) : [null];
        uid = guest && !g ? guest : newUid();     // 손님이었으면 그 기록에 계정을 붙인다
        const now = new Date().toISOString();
        await kv([
          ['SET', key, uid],
          ['HSET', `user:${uid}`, 'provider', provider],
          ['HSETNX', `user:${uid}`, 'createdAt', now],
          ['HSETNX', `user:${uid}`, 'nick', `예측러${String(parseInt(uid.slice(0, 6), 16) % 10000).padStart(4, '0')}`],
        ]);
      }
      setUid(res, uid);
      return go(res, `${BACK}?login=ok`);
    } catch (e) {
      return go(res, `${BACK}?login=failed`);
    }
  }
  return go(res, BACK);
};
