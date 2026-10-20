// 초안 승인 버튼 처리 (텔레그램 웹훅). 2026-10-20 'AI가 쓰고, 사람이 승인하고, 발행'.
//
//   POST /api/review                       텔레그램이 보내는 버튼 클릭(callback_query)
//   GET  /api/review?setup=1&key=<비밀값>   웹훅 등록 (환경변수를 넣은 뒤 한 번만)
//
// [발행] → GitHub 'publish-draft' 워크플로를 slug 와 함께 실행 → 워크플로가 Upstash 의 초안을
//          꺼내 발행하고, 끝나면 텔레그램으로 링크를 보낸다.
// [보류] → Upstash 의 초안을 지운다.
// 관리자 대화(TELEGRAM_ADMIN_CHAT_ID)에서 온 클릭만 받는다.
//
// 환경변수 (Vercel, factorysignal-magazine):
//   TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID, TELEGRAM_WEBHOOK_SECRET,
//   GITHUB_DISPATCH_TOKEN (이 저장소 Actions 쓰기 권한만 있는 토큰), KV_REST_API_* (자동)
const REPO = 'minjh8768-al/factorysignal-magazine';
const BOT = process.env.TELEGRAM_BOT_TOKEN;
const ADMIN = String(process.env.TELEGRAM_ADMIN_CHAT_ID || '');
const SECRET = process.env.TELEGRAM_WEBHOOK_SECRET;
const GH = process.env.GITHUB_DISPATCH_TOKEN;
const KV_URL = process.env.KV_REST_API_URL;
const KV_TOKEN = process.env.KV_REST_API_TOKEN;
const SLUG_RE = /^[a-z0-9][a-z0-9-]{2,119}$/;

async function tg(method, params) {
  const r = await fetch(`https://api.telegram.org/bot${BOT}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params),
  });
  return r.json();
}

async function kv(commands) {
  const r = await fetch(`${KV_URL}/pipeline`, {
    method: 'POST', headers: { Authorization: `Bearer ${KV_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(commands),
  });
  return (await r.json()).map((x) => x.result);
}

async function dispatch(slug) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/publish-draft.yml/dispatches`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${GH}`, Accept: 'application/vnd.github+json', 'User-Agent': 'factory-magazine' },
    body: JSON.stringify({ ref: 'main', inputs: { slug } }),
  });
  return r.status === 204;
}

module.exports = async (req, res) => {
  if (!BOT || !ADMIN || !SECRET) return res.status(503).json({ error: '승인 기능 설정이 없습니다.' });

  if (req.method === 'GET') {
    if (req.query.setup !== '1' || req.query.key !== SECRET) return res.status(404).end();
    const host = req.headers['x-forwarded-host'] || req.headers.host;
    const out = await tg('setWebhook', {
      url: `https://${host}/api/review`, secret_token: SECRET, allowed_updates: ['callback_query'],
    });
    return res.json(out);
  }

  if (req.headers['x-telegram-bot-api-secret-token'] !== SECRET) return res.status(401).end();
  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
  const cq = body.callback_query;
  if (!cq) return res.json({ ok: true });

  const chatId = String(cq.message && cq.message.chat && cq.message.chat.id);
  const [action, slug] = String(cq.data || '').split(':');
  if (chatId !== ADMIN || !SLUG_RE.test(slug || '')) {
    await tg('answerCallbackQuery', { callback_query_id: cq.id, text: '처리할 수 없는 요청입니다.' });
    return res.json({ ok: true });
  }

  let note;
  if (action === 'pub') {
    const exists = (await kv([['EXISTS', `draft:${slug}`]]))[0];
    if (!exists) note = '이미 처리됐거나 7일이 지난 초안입니다.';
    else note = (await dispatch(slug)) ? '✅ 발행을 시작했어요 (1~3분). 끝나면 링크를 보내 드려요.' : '⚠️ 발행 요청 실패 (GitHub 토큰 확인 필요)';
  } else if (action === 'skip') {
    await kv([['DEL', `draft:${slug}`]]);
    note = '⏸ 보류했어요. 이 초안은 발행되지 않습니다.';
  } else {
    note = '알 수 없는 버튼입니다.';
  }
  await tg('answerCallbackQuery', { callback_query_id: cq.id, text: note.slice(0, 190) });
  // 버튼을 없애고 결과를 메시지 아래에 남긴다 (같은 초안을 두 번 누르지 않게).
  await tg('editMessageReplyMarkup', { chat_id: chatId, message_id: cq.message.message_id, reply_markup: { inline_keyboard: [] } });
  await tg('sendMessage', { chat_id: chatId, reply_to_message_id: cq.message.message_id, text: note });
  return res.json({ ok: true });
};
