'use strict';
/*
 * 모모 가계부 서버 (의존성 없음, Node 18+)
 * - public/ 정적 파일 제공
 * - Gemini API 프록시: API 키는 서버 환경변수에만 존재하고 클라이언트로 보내지 않는다.
 * - 거래 데이터는 서버에 저장하지 않는다(브라우저 저장). 이미지도 메모리에서만 처리하고 버린다.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

loadDotEnv(path.join(__dirname, '.env'));

const PORT = Number(process.env.PORT) || 8787;
const API_KEY = process.env.GEMINI_API_KEY || '';
const MODEL = process.env.GEMINI_MODEL || 'gemini-2.5-flash';
const RATE_PER_MIN = Number(process.env.AI_RATE_PER_MIN) || 5;
const DAILY_LIMIT = Number(process.env.AI_DAILY_LIMIT) || 100;
const PUBLIC_DIR = path.join(__dirname, 'public');
const MAX_BODY = 8 * 1024 * 1024;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.webmanifest': 'application/manifest+json',
};

const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'X-Frame-Options': 'DENY',
  'Content-Security-Policy':
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'",
};

function loadDotEnv(file) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); } catch { return; }
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (!m || line.trim().startsWith('#')) continue;
    const value = m[2].replace(/^["']|["']$/g, '');
    if (!(m[1] in process.env)) process.env[m[1]] = value;
  }
}

/* ---------- 사용량 제한 (무료 한도 보호) ---------- */
const hits = new Map();
let daily = { day: '', count: 0 };

function allowRequest(ip) {
  const now = Date.now();
  const day = new Date().toISOString().slice(0, 10);
  if (daily.day !== day) daily = { day, count: 0 };
  if (daily.count >= DAILY_LIMIT) return '오늘 AI 사용량을 모두 썼어요. 내일 다시 시도해 주세요.';
  const list = (hits.get(ip) || []).filter((t) => now - t < 60_000);
  if (list.length >= RATE_PER_MIN) return 'AI 요청이 너무 잦아요. 1분 뒤에 다시 시도해 주세요.';
  list.push(now);
  hits.set(ip, list);
  daily.count += 1;
  return null;
}

/* ---------- 공통 유틸 ---------- */
function send(res, status, body, headers = {}) {
  res.writeHead(status, { ...SECURITY_HEADERS, ...headers });
  res.end(body);
}
function sendJson(res, status, obj) {
  send(res, status, JSON.stringify(obj), { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > MAX_BODY) { reject(new HttpError(413, '파일이 너무 커요. 더 작은 이미지로 시도해 주세요.')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')); }
      catch { reject(new HttpError(400, '요청 형식이 올바르지 않아요.')); }
    });
    req.on('error', reject);
  });
}

class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

const isISO = (s) => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s + 'T00:00:00Z'));
const clip = (v, n) => String(v ?? '').replace(/[\u0000-\u001f]/g, ' ').trim().slice(0, n);

function weekdayKo(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return '일월화수목금토'[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] + '요일';
}

function cleanCategories(list) {
  if (!Array.isArray(list)) return [];
  return list.slice(0, 40).map((c) => ({
    id: clip(c.id, 30),
    name: clip(c.name, 20),
    type: c.type === 'income' ? 'income' : 'expense',
  })).filter((c) => c.id && c.name);
}

/* ---------- Gemini 호출 ---------- */
async function callGemini(parts, { json = true, temperature = 0.1 } = {}) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(MODEL)}:generateContent`;
  const body = {
    contents: [{ role: 'user', parts }],
    generationConfig: { temperature, maxOutputTokens: 8192, ...(json ? { responseMimeType: 'application/json' } : {}) },
  };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 45_000);
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': API_KEY },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
  } catch {
    throw new HttpError(502, 'AI 서버에 연결하지 못했어요.');
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    if (res.status === 429) throw new HttpError(429, 'Gemini 무료 사용량 한도에 도달했어요. 잠시 후 다시 시도해 주세요.');
    if (res.status === 400 || res.status === 404) throw new HttpError(502, `AI 요청이 거절됐어요(${res.status}). 서버의 GEMINI_MODEL 설정을 확인해 주세요.`);
    if (res.status === 401 || res.status === 403) throw new HttpError(502, 'Gemini API 키를 확인해 주세요.');
    throw new HttpError(502, `AI 요청이 실패했어요(${res.status}).`);
  }
  const data = await res.json();
  const text = (data?.candidates?.[0]?.content?.parts || []).map((p) => p.text || '').join('');
  if (!text) throw new HttpError(502, 'AI가 답을 만들지 못했어요. 다시 시도해 주세요.');
  if (!json) return text.trim();
  try {
    return JSON.parse(text.replace(/^```(?:json)?\s*|\s*```$/g, ''));
  } catch {
    throw new HttpError(502, 'AI 응답을 읽지 못했어요. 다시 시도해 주세요.');
  }
}

/* AI가 돌려준 값은 그대로 믿지 않고 검증한다. 불확실한 값은 비우고 uncertain 표시 → 사용자 확인 필수 */
function sanitizeItems(raw, categories, today) {
  const list = Array.isArray(raw?.items) ? raw.items : Array.isArray(raw) ? raw : [];
  const byId = new Map(categories.map((c) => [c.id, c]));
  const byName = new Map(categories.map((c) => [c.name, c]));
  const allowed = ['date', 'amount', 'type', 'merchant', 'category'];
  return list.slice(0, 60).map((it) => {
    const uncertain = new Set(Array.isArray(it?.uncertain) ? it.uncertain.filter((u) => allowed.includes(u)) : []);
    const n = Number(String(it?.amount ?? '').replace(/[^\d.-]/g, ''));
    let amount = Number.isFinite(n) && n > 0 && n < 1e11 ? Math.round(n) : null;
    if (amount === null) uncertain.add('amount');
    let date = isISO(it?.date) ? it.date : null;
    if (date && date > today) { uncertain.add('date'); }
    if (!date) uncertain.add('date');
    const type = it?.type === 'income' ? 'income' : 'expense';
    const cat = byId.get(it?.category) || byName.get(it?.category);
    const category = cat && cat.type === type ? cat.id : null;
    if (!category) uncertain.add('category');
    return {
      date,
      time: /^\d{2}:\d{2}$/.test(it?.time || '') ? it.time : '',
      merchant: clip(it?.merchant, 40),
      amount,
      type,
      category,
      memo: clip(it?.memo, 80),
      uncertain: [...uncertain],
    };
  });
}

function categoryLines(categories) {
  return categories.map((c) => `- ${c.id}: ${c.name} (${c.type === 'income' ? '수입' : '지출'})`).join('\n');
}

const ITEM_SCHEMA = '{"items":[{"date":"YYYY-MM-DD 또는 null","time":"HH:MM 또는 \\"\\"","merchant":"사용처","amount":정수 또는 null,"type":"expense 또는 income","category":"카테고리 id","memo":"","uncertain":["date"|"amount"|"type"|"merchant"|"category"]}]}';

async function handleParse(body) {
  const text = clip(body.text, 1000);
  const today = isISO(body.today) ? body.today : new Date().toISOString().slice(0, 10);
  const categories = cleanCategories(body.categories);
  if (!text) throw new HttpError(400, '내용을 입력해 주세요.');
  const prompt = `너는 가계부 입력 해석기다. 사용자의 문장에서 거래를 추출해 JSON으로만 답한다.
오늘: ${today} (${weekdayKo(today)})
카테고리 목록:
${categoryLines(categories)}

규칙:
1. 문장에 명시된 거래만 추출한다. 언급되지 않은 거래를 추측해서 만들지 않는다.
2. amount는 원 단위 정수다. "1만2천원"=12000, "6,500원"=6500. 금액이 없거나 모호하면 null로 두고 uncertain에 "amount"를 넣는다.
3. date는 오늘 기준으로 변환한다(오늘/어제/그제/지난주 금요일/15일 등). 날짜 언급이 없으면 오늘 날짜를 쓴다. 해석이 모호하면 null + uncertain "date".
4. 지출은 "expense", 수입(월급, 용돈 받음, 입금 등)은 "income".
5. category는 목록의 id만 쓴다. 판단이 어려우면 가장 가까운 것을 고르고 uncertain에 "category"를 넣는다.
6. merchant는 가게·거래처 이름. 없으면 무엇에 썼는지 짧게 쓴다.
출력 형식: ${ITEM_SCHEMA}

문장: """${text}"""`;
  const raw = await callGemini([{ text: prompt }]);
  return { items: sanitizeItems(raw, categories, today) };
}

async function handleOcr(body) {
  const image = typeof body.image === 'string' ? body.image : '';
  const mimeType = ['image/jpeg', 'image/png', 'image/webp'].includes(body.mimeType) ? body.mimeType : 'image/jpeg';
  const today = isISO(body.today) ? body.today : new Date().toISOString().slice(0, 10);
  const categories = cleanCategories(body.categories);
  if (!image || !/^[A-Za-z0-9+/=]+$/.test(image.slice(0, 200))) throw new HttpError(400, '이미지를 읽지 못했어요.');
  const prompt = `이 이미지는 사용자가 직접 올린 은행·카드 앱 거래내역 캡처다. 보이는 거래를 한 건씩 추출해 JSON으로만 답한다.
오늘: ${today}
카테고리 목록:
${categoryLines(categories)}

규칙:
1. 이미지에 실제로 보이는 거래만 추출한다. 보이지 않는 거래를 만들지 않는다.
2. amount는 그 거래의 금액(원, 정수)이다. "잔액"·"누적"·"한도" 숫자는 금액이 아니다.
3. 숫자나 글자가 흐리거나 잘려서 확실하지 않으면 그 값을 null로 두고 uncertain에 필드명을 넣는다. 절대 추측으로 채우지 않는다.
4. 연도가 안 보이면 오늘 기준으로 가장 가까운 과거 날짜의 연도를 쓰고, 월·일이 불확실하면 date=null + uncertain "date".
5. 출금·결제·승인은 "expense", 입금은 "income". 승인 취소·환불 건은 memo에 "취소"를 쓰고 uncertain에 "type"을 넣는다.
6. 시간이 보이면 time에 HH:MM, 없으면 "".
7. category는 목록의 id만 쓴다. 판단이 어려우면 uncertain에 "category".
출력 형식: ${ITEM_SCHEMA}
거래가 하나도 안 보이면 {"items":[]}`;
  const raw = await callGemini([{ text: prompt }, { inline_data: { mime_type: mimeType, data: image } }]);
  return { items: sanitizeItems(raw, categories, today) };
}

async function handleChat(body) {
  const question = clip(body.question, 600);
  const mode = body.mode === 'report' ? 'report' : 'chat';
  let context = '{}';
  try { context = JSON.stringify(body.context ?? {}).slice(0, 12000); } catch { /* ignore */ }
  if (mode === 'chat' && !question) throw new HttpError(400, '질문을 입력해 주세요.');
  const rules = `너는 다정하지만 정확한 가계부 코치 '모모'다.
[통계]는 앱이 사용자의 실제 거래 기록으로 계산한 값이다.
- 금액·비율은 [통계]에 있는 값만 인용한다. 새로 계산하거나 추정한 숫자를 만들지 않는다. 필요한 값이 없으면 "그 내용은 기록 데이터가 부족해요"라고 말한다.
- 거래를 추가·수정·삭제했다고 말하지 않는다. 너는 기록을 바꿀 수 없다.
- 기록이 없는 날을 실제로 지출이 있었다고 단정하지 않는다. "기록이 빠졌을 수 있어요" 정도로만 안내한다.
- 해요체, 간결하게. 이모지는 최대 1개. 마크다운 표는 쓰지 않는다.`;
  const task = mode === 'report'
    ? `[통계]의 month 기준 월간 소비 리포트를 작성한다. 다음 순서로 짧은 소제목과 1~3줄씩: 한눈에 보기 / 잘한 점 / 신경 쓸 점(과소비·예산 초과 위험) / 다음 달 절약 제안 3가지 / 기록 점검(누락 가능성). 전체 18줄 이내.`
    : `사용자 질문에 3~6문장으로 답한다.\n[질문] ${question}`;
  const text = await callGemini([{ text: `${rules}\n\n[통계]\n${context}\n\n${task}` }], { json: false, temperature: 0.4 });
  return { text: text.slice(0, 4000) };
}

/* ---------- 라우팅 ---------- */
const routes = { '/api/parse': handleParse, '/api/ocr': handleOcr, '/api/chat': handleChat };

async function handleApi(req, res, pathname) {
  if (pathname === '/api/status' && req.method === 'GET') {
    return sendJson(res, 200, { ai: Boolean(API_KEY), model: API_KEY ? MODEL : null });
  }
  const handler = routes[pathname];
  if (!handler) return sendJson(res, 404, { error: '없는 주소예요.' });
  if (req.method !== 'POST') return sendJson(res, 405, { error: 'POST만 지원해요.' });
  const origin = req.headers.origin;
  if (origin && new URL(origin).host !== req.headers.host) return sendJson(res, 403, { error: '허용되지 않은 요청이에요.' });
  if (!API_KEY) return sendJson(res, 503, { error: 'AI가 아직 연결되지 않았어요. 서버에 GEMINI_API_KEY를 설정해 주세요.' });
  const limited = allowRequest(req.socket.remoteAddress || 'unknown');
  if (limited) return sendJson(res, 429, { error: limited });
  try {
    const body = await readJson(req);
    sendJson(res, 200, await handler(body));
  } catch (err) {
    const status = err instanceof HttpError ? err.status : 500;
    if (status === 500) console.error('[api]', pathname, err.message); // 요청 본문(금융정보)은 로그에 남기지 않는다
    sendJson(res, status, { error: err instanceof HttpError ? err.message : '서버 오류가 발생했어요.' });
  }
}

function serveStatic(req, res, pathname) {
  if (req.method !== 'GET' && req.method !== 'HEAD') return send(res, 405, 'Method Not Allowed');
  let rel;
  try { rel = decodeURIComponent(pathname); } catch { return send(res, 400, 'Bad Request'); }
  if (rel.endsWith('/')) rel += 'index.html';
  const file = path.normalize(path.join(PUBLIC_DIR, rel));
  if (!file.startsWith(PUBLIC_DIR + path.sep)) return send(res, 403, 'Forbidden');
  fs.readFile(file, (err, data) => {
    if (err) return send(res, 404, 'Not Found', { 'Content-Type': 'text/plain; charset=utf-8' });
    send(res, 200, req.method === 'HEAD' ? undefined : data, {
      'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-cache',
    });
  });
}

const server = http.createServer((req, res) => {
  const { pathname } = new URL(req.url, 'http://localhost');
  if (pathname.startsWith('/api/')) {
    handleApi(req, res, pathname).catch(() => sendJson(res, 500, { error: '서버 오류가 발생했어요.' }));
  } else {
    serveStatic(req, res, pathname);
  }
});

if (require.main === module) {
  server.listen(PORT, () => {
    console.log(`모모 가계부: http://localhost:${PORT}`);
    console.log(API_KEY ? `Gemini 연결됨 (모델: ${MODEL})` : 'GEMINI_API_KEY 없음 → AI 기능 없이 실행 (로컬 해석기 사용)');
  });
}

module.exports = { sanitizeItems, server };
