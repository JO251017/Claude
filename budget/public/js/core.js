'use strict';
/* 모모 가계부 – 데이터·계산 로직 (DOM 없음). 모든 금액 계산은 이 파일의 코드가 한다. */

const STORAGE_KEY = 'momo-budget-v1';
const AUTO_BACKUP_KEY = 'momo-budget-v1-autobackup';
const SCHEMA_VERSION = 1;

const DEFAULT_CATEGORIES = [
  { id: 'food', name: '식비', icon: '🍚', type: 'expense', color: '#F4A7B9' },
  { id: 'cafe', name: '카페·간식', icon: '☕', type: 'expense', color: '#C9A7EB' },
  { id: 'transport', name: '교통', icon: '🚌', type: 'expense', color: '#8FCFC0' },
  { id: 'shopping', name: '쇼핑', icon: '🛍️', type: 'expense', color: '#F7C08A' },
  { id: 'living', name: '생활', icon: '🧴', type: 'expense', color: '#9DBFE3' },
  { id: 'housing', name: '주거·통신', icon: '🏠', type: 'expense', color: '#B3B6E6' },
  { id: 'health', name: '의료·건강', icon: '💊', type: 'expense', color: '#EFA9C9' },
  { id: 'culture', name: '문화·여가', icon: '🎬', type: 'expense', color: '#F5D08A' },
  { id: 'education', name: '교육', icon: '📚', type: 'expense', color: '#BFDDA0' },
  { id: 'gift', name: '경조사·선물', icon: '🎁', type: 'expense', color: '#E3A8AE' },
  { id: 'etc', name: '기타', icon: '✨', type: 'expense', color: '#D6CCC6' },
  { id: 'salary', name: '급여', icon: '💰', type: 'income', color: '#93CDB0' },
  { id: 'allowance', name: '용돈', icon: '💌', type: 'income', color: '#F6B8C6' },
  { id: 'side', name: '부수입', icon: '🌱', type: 'income', color: '#A9D8C8' },
  { id: 'income_etc', name: '기타수입', icon: '🪙', type: 'income', color: '#D9C8F0' },
];

const CATEGORY_KEYWORDS = {
  cafe: ['스타벅스', '스벅', '커피', '카페', '이디야', '투썸', '메가커피', '메가mgc', '빽다방', '컴포즈', '폴바셋', '블루보틀', '할리스', '파리바게뜨', '뚜레쥬르', '베이커리', '빵', '디저트', '케이크', '아이스크림', '배스킨', '던킨', '간식', '편의점', 'gs25', 'cu', '세븐일레븐', '이마트24', '공차', '라떼', '아메리카노'],
  food: ['식당', '김밥', '점심', '저녁', '아침', '밥', '배달', '배민', '배달의민족', '요기요', '쿠팡이츠', '맥도날드', '버거', '롯데리아', '치킨', '피자', '국밥', '분식', '떡볶이', '마라', '초밥', '고기', '술', '이마트', '홈플러스', '롯데마트', '마트', '장보기', '식료품', '외식', '마켓컬리', '컬리'],
  transport: ['버스', '지하철', '택시', '카카오t', '카카오택시', '교통', '주유', '기름', 'ktx', '코레일', 'srt', '티머니', '주차', '톨게이트', '하이패스', '따릉이', '킥보드', '고속버스'],
  shopping: ['쿠팡', '무신사', '지그재그', '에이블리', '올리브영', '옷', '신발', '가방', '29cm', '11번가', 'g마켓', '지마켓', '옥션', 'ssg', '백화점', '화장품', '알리', '테무', '아울렛'],
  living: ['다이소', '생필품', '세탁', '세제', '휴지', '미용실', '헤어', '네일', '수선', '택배', '이케아'],
  housing: ['월세', '관리비', '전기', '가스', '수도', '통신', '휴대폰', '핸드폰', 'skt', 'kt', 'lg u+', '유플러스', '인터넷', '보험'],
  health: ['병원', '약국', '의원', '치과', '한의원', '안과', '피부과', '약', '헬스', '필라테스', '요가', 'pt'],
  culture: ['cgv', '메가박스', '롯데시네마', '영화', '넷플릭스', '유튜브', '멜론', '스포티파이', '티빙', '왓챠', '디즈니', '공연', '전시', '콘서트', '여행', '숙소', '호텔', '에어비앤비', '게임', '노래방', 'pc방'],
  education: ['학원', '교재', '강의', '인강', '클래스101', '인프런', '서점', '교보문고', '예스24', '알라딘', '책', '시험', '자격증'],
  gift: ['축의금', '조의금', '부조', '선물', '생일', '꽃', '기념일'],
  salary: ['월급', '급여', '상여', '보너스', '성과급', '인센티브'],
  allowance: ['용돈'],
  side: ['부수입', '알바', '중고', '당근', '번개장터', '프리랜서', '외주', '판매'],
  income_etc: ['환급', '이자', '캐시백', '환불', '페이백'],
};

const ITEMS = [
  { id: 'ribbon', name: '핑크 리본', icon: '🎀' },
  { id: 'glasses', name: '동글 안경', icon: '👓' },
  { id: 'flower', name: '라벤더 꽃', icon: '🌸' },
  { id: 'scarf', name: '포근 목도리', icon: '🧣' },
  { id: 'crown', name: '반짝 왕관', icon: '👑' },
];

const STAGES = [
  { min: 0, name: '아기 모모', desc: '이제 막 기록을 시작했어요' },
  { min: 1, name: '꼬마 모모', desc: '예산을 한 달 지켰어요' },
  { min: 3, name: '반짝 모모', desc: '예산을 세 달 지켰어요' },
  { min: 6, name: '든든 모모', desc: '여섯 달 동안 계획대로 소비했어요' },
];

const XP_RULES = { activeDay: 10, keptMonth: 100, goalAchieved: 150, missionDone: 30 };
const XP_PER_LEVEL = 150;

/* ---------- 날짜 ---------- */
const pad = (n) => String(n).padStart(2, '0');
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
function toISO(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
function parseISO(s) { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }
function todayISO() { return toISO(new Date()); }
function addDays(iso, n) { const d = parseISO(iso); d.setDate(d.getDate() + n); return toISO(d); }
function monthOf(iso) { return iso.slice(0, 7); }
function addMonths(mk, n) { const [y, m] = mk.split('-').map(Number); const d = new Date(y, m - 1 + n, 1); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; }
function daysInMonth(mk) { const [y, m] = mk.split('-').map(Number); return new Date(y, m, 0).getDate(); }
function isValidISO(s) { return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && toISO(parseISO(s)) === s; }
function weekStart(iso) { const d = parseISO(iso); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return toISO(d); }
function weekdayOf(iso) { return parseISO(iso).getDay(); }
function diffDays(a, b) { return Math.round((parseISO(b) - parseISO(a)) / 86400000); }
function dateRange(from, to) { const out = []; for (let d = from; d <= to; d = addDays(d, 1)) out.push(d); return out; }
function monthLabel(mk) { const [y, m] = mk.split('-').map(Number); return `${y}년 ${m}월`; }
function dayLabel(iso) { const d = parseISO(iso); return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEKDAYS[d.getDay()]})`; }

/* ---------- 포맷 ---------- */
function formatWon(n) { return `${Math.round(n || 0).toLocaleString('ko-KR')}원`; }
function formatPct(p) { return p == null ? '-' : `${p > 0 ? '+' : ''}${Math.round(p)}%`; }
function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
function normalizeMerchant(s) { return String(s || '').toLowerCase().replace(/\(주\)|주식회사|㈜/g, '').replace(/[\s·.\-_/]/g, ''); }

/* ---------- 데이터 구조 ---------- */
function createEmptyData() {
  const now = new Date().toISOString();
  return {
    version: SCHEMA_VERSION,
    profile: { name: '' },
    transactions: [],
    categories: DEFAULT_CATEGORIES.map((c) => ({ ...c })),
    budgets: {},            // { 'YYYY-MM': { total, byCategory: { catId: amount } } }
    goals: [],              // { id, name, target, deposits:[{id,date,amount}], createdAt, achievedAt }
    dayChecks: {},          // { 'YYYY-MM-DD': 'nospend' | 'ok' } 사용자가 직접 확인한 날
    character: { equipped: null },
    aiReports: [],          // { month, text, createdAt }
    uploads: [],            // { id, createdAt, fileName, found, saved } – 이미지 자체는 저장하지 않음
    meta: { createdAt: now, lastBackupAt: null },
  };
}

const TX_SOURCES = ['manual', 'quick', 'nl', 'voice', 'image', 'batch'];
function normalizeTx(t) {
  if (!t || typeof t !== 'object') return null;
  const amount = Math.round(Number(t.amount));
  if (!Number.isFinite(amount) || amount <= 0 || amount >= 1e11) return null;
  if (!isValidISO(t.date)) return null;
  const now = new Date().toISOString();
  return {
    id: String(t.id || uid()),
    date: t.date,
    time: /^\d{2}:\d{2}$/.test(t.time || '') ? t.time : '',
    type: t.type === 'income' ? 'income' : 'expense',
    amount,
    category: String(t.category || (t.type === 'income' ? 'income_etc' : 'etc')),
    merchant: String(t.merchant || '').trim().slice(0, 60),
    memo: String(t.memo || '').trim().slice(0, 200),
    source: TX_SOURCES.includes(t.source) ? t.source : 'manual',
    createdAt: t.createdAt || now,
    updatedAt: t.updatedAt || t.createdAt || now,
  };
}

function normalizeData(raw) {
  const base = createEmptyData();
  if (!raw || typeof raw !== 'object') return base;
  const out = base;
  if (raw.profile && typeof raw.profile === 'object') out.profile.name = String(raw.profile.name || '').slice(0, 20);
  if (Array.isArray(raw.categories) && raw.categories.length) {
    const seen = new Set();
    out.categories = raw.categories.filter((c) => c && c.id && c.name && !seen.has(c.id) && seen.add(c.id)).map((c) => ({
      id: String(c.id).slice(0, 30), name: String(c.name).slice(0, 20), icon: String(c.icon || '✨').slice(0, 4),
      type: c.type === 'income' ? 'income' : 'expense', color: /^#[0-9a-f]{6}$/i.test(c.color) ? c.color : '#D6CCC6',
    }));
    for (const id of ['etc', 'income_etc']) {
      if (!out.categories.some((c) => c.id === id)) out.categories.push({ ...DEFAULT_CATEGORIES.find((c) => c.id === id) });
    }
  }
  const catIds = new Set(out.categories.map((c) => c.id));
  out.transactions = (Array.isArray(raw.transactions) ? raw.transactions : []).map(normalizeTx).filter(Boolean).map((t) => {
    if (!catIds.has(t.category)) t.category = t.type === 'income' ? 'income_etc' : 'etc';
    return t;
  });
  if (raw.budgets && typeof raw.budgets === 'object') {
    for (const [mk, b] of Object.entries(raw.budgets)) {
      if (!/^\d{4}-\d{2}$/.test(mk) || !b) continue;
      const byCategory = {};
      for (const [cid, v] of Object.entries(b.byCategory || {})) { const n = Math.round(Number(v)); if (n > 0 && catIds.has(cid)) byCategory[cid] = n; }
      out.budgets[mk] = { total: Math.max(0, Math.round(Number(b.total) || 0)), byCategory };
    }
  }
  out.goals = (Array.isArray(raw.goals) ? raw.goals : []).filter((g) => g && g.name).map((g) => ({
    id: String(g.id || uid()), name: String(g.name).slice(0, 30), target: Math.max(1, Math.round(Number(g.target) || 1)),
    deposits: (Array.isArray(g.deposits) ? g.deposits : []).filter((d) => d && isValidISO(d.date) && Number(d.amount))
      .map((d) => ({ id: String(d.id || uid()), date: d.date, amount: Math.round(Number(d.amount)) })),
    createdAt: g.createdAt || new Date().toISOString(), achievedAt: g.achievedAt || null,
  }));
  if (raw.dayChecks && typeof raw.dayChecks === 'object') {
    for (const [d, v] of Object.entries(raw.dayChecks)) if (isValidISO(d) && (v === 'nospend' || v === 'ok')) out.dayChecks[d] = v;
  }
  if (raw.character && ITEMS.some((i) => i.id === raw.character.equipped)) out.character.equipped = raw.character.equipped;
  out.aiReports = (Array.isArray(raw.aiReports) ? raw.aiReports : []).filter((r) => r && r.text).slice(-24);
  out.uploads = (Array.isArray(raw.uploads) ? raw.uploads : []).filter(Boolean).slice(-50);
  if (raw.meta) { out.meta.createdAt = raw.meta.createdAt || out.meta.createdAt; out.meta.lastBackupAt = raw.meta.lastBackupAt || null; }
  return out;
}

/* 저장소: localStorage + 하루 1회 자동 백업 사본 */
function createStore(storage) {
  let data = createEmptyData();
  let lastError = null;
  function load() {
    try {
      const raw = storage.getItem(STORAGE_KEY);
      data = raw ? normalizeData(JSON.parse(raw)) : createEmptyData();
    } catch (e) {
      lastError = e;
      try {
        const backup = JSON.parse(storage.getItem(AUTO_BACKUP_KEY) || 'null');
        data = normalizeData(backup && backup.data);
      } catch { data = createEmptyData(); }
    }
    return data;
  }
  function save() {
    try {
      const today = todayISO();
      const prev = storage.getItem(STORAGE_KEY);
      const backup = JSON.parse(storage.getItem(AUTO_BACKUP_KEY) || 'null');
      if (prev && (!backup || backup.date !== today)) storage.setItem(AUTO_BACKUP_KEY, JSON.stringify({ date: today, data: JSON.parse(prev) }));
      storage.setItem(STORAGE_KEY, JSON.stringify(data));
      lastError = null;
      return true;
    } catch (e) { lastError = e; return false; }
  }
  return {
    get data() { return data; },
    get lastError() { return lastError; },
    load, save,
    replace(next) { data = normalizeData(next); return save(); },
  };
}

/* ---------- 조회 헬퍼 ---------- */
function catMap(data) { return new Map(data.categories.map((c) => [c.id, c])); }
function getCategory(data, id) { return data.categories.find((c) => c.id === id) || data.categories.find((c) => c.id === 'etc'); }
function txBetween(data, from, to, type) {
  return data.transactions.filter((t) => t.date >= from && t.date <= to && (!type || t.type === type));
}
const sumAmount = (list) => list.reduce((s, t) => s + t.amount, 0);
function pctChange(cur, base) { return base > 0 ? ((cur - base) / base) * 100 : null; }
function monthStart(mk) { return `${mk}-01`; }
function monthEnd(mk) { return `${mk}-${pad(daysInMonth(mk))}`; }

/* 예산: 해당 월 설정이 없으면 가장 최근 이전 달 설정을 이어서 쓴다 */
function getBudget(data, mk) {
  if (data.budgets[mk]) return { ...data.budgets[mk], inherited: false };
  const prev = Object.keys(data.budgets).filter((k) => k < mk).sort().pop();
  return prev ? { ...data.budgets[prev], inherited: true } : { total: 0, byCategory: {}, inherited: false };
}

function activeDaySet(data, upTo) {
  const set = new Set();
  for (const t of data.transactions) if (!upTo || t.date <= upTo) set.add(t.date);
  for (const [d, v] of Object.entries(data.dayChecks)) if (v === 'nospend' && (!upTo || d <= upTo)) set.add(d);
  return set;
}

function computeStreak(data, today) {
  const set = activeDaySet(data, today);
  let d = set.has(today) ? today : addDays(today, -1);
  let n = 0;
  while (set.has(d)) { n += 1; d = addDays(d, -1); }
  return n;
}

/* ---------- 누락 가능성 탐지 ----------
 * 기록이 없다고 지출이 있었다고 가정하지 않는다. "확인이 필요한 날"만 알려준다.
 * empty: 기록도 '지출 없음' 확인도 없는 날 / low: 평소보다 지출 기록이 눈에 띄게 적은 날 */
function detectMissing(data, today, lookback = 30) {
  if (!data.transactions.length) return [];
  const first = data.transactions.reduce((m, t) => (t.date < m ? t.date : m), today);
  const from = [first, addDays(today, -lookback)].sort().pop();
  const to = addDays(today, -1);
  if (from > to) return [];
  const byDay = new Map();
  for (const t of data.transactions) {
    if (t.type !== 'expense') continue;
    const cur = byDay.get(t.date) || { amount: 0, count: 0 };
    cur.amount += t.amount; cur.count += 1; byDay.set(t.date, cur);
  }
  const recent = [...byDay.entries()].filter(([d]) => d >= addDays(today, -60) && d < today).map(([, v]) => v.amount).sort((a, b) => a - b);
  const median = recent.length ? recent[Math.floor(recent.length / 2)] : 0;
  const hasAny = new Set(data.transactions.map((t) => t.date));
  const out = [];
  for (const d of dateRange(from, to)) {
    if (data.dayChecks[d]) continue;
    if (!hasAny.has(d)) { out.push({ date: d, kind: 'empty' }); continue; }
    const day = byDay.get(d);
    if (recent.length >= 10 && median >= 10000 && day && day.amount < median * 0.2) {
      out.push({ date: d, kind: 'low', amount: day.amount });
    }
  }
  return out;
}

/* ---------- 카테고리 추천 (기록 학습 → 키워드 → 기본값) ---------- */
function suggestCategory(data, text, type = 'expense') {
  const norm = normalizeMerchant(text);
  if (!norm) return { id: type === 'income' ? 'income_etc' : 'etc', reason: 'default' };
  const valid = new Set(data.categories.filter((c) => c.type === type).map((c) => c.id));
  const hist = [...data.transactions].reverse().find((t) => t.type === type && t.merchant && normalizeMerchant(t.merchant) === norm && valid.has(t.category));
  if (hist) return { id: hist.category, reason: 'history' };
  let best = null;
  for (const [cid, words] of Object.entries(CATEGORY_KEYWORDS)) {
    if (!valid.has(cid)) continue;
    for (const w of words) {
      const nw = normalizeMerchant(w);
      if (nw && norm.includes(nw) && (!best || nw.length > best.len)) best = { id: cid, len: nw.length };
    }
  }
  if (best) return { id: best.id, reason: 'keyword' };
  return { id: type === 'income' ? 'income_etc' : 'etc', reason: 'default' };
}

/* 자주 쓰는 지출: 최근 90일 같은 사용처·금액 반복 */
function computeQuickItems(data, today, limit = 6) {
  const from = addDays(today, -90);
  const groups = new Map();
  for (const t of data.transactions) {
    if (t.type !== 'expense' || t.date < from || !t.merchant) continue;
    const key = `${normalizeMerchant(t.merchant)}|${t.category}|${t.amount}`;
    const g = groups.get(key) || { merchant: t.merchant, category: t.category, amount: t.amount, count: 0, last: '' };
    g.count += 1; if (t.date > g.last) g.last = t.date;
    groups.set(key, g);
  }
  return [...groups.values()].filter((g) => g.count >= 2)
    .sort((a, b) => b.count - a.count || (a.last < b.last ? 1 : -1)).slice(0, limit);
}

/* 중복 검사: 같은 날짜·금액·유형이면서 사용처가 비슷하거나 한쪽이 비어 있으면 중복 후보 */
function findDuplicate(data, item) {
  if (!item.date || !item.amount) return null;
  const a = normalizeMerchant(item.merchant);
  return data.transactions.find((t) => {
    if (t.date !== item.date || t.amount !== item.amount || t.type !== item.type) return false;
    const b = normalizeMerchant(t.merchant);
    return !a || !b || a.includes(b) || b.includes(a);
  }) || null;
}

/* ---------- 통계 ----------
 * mk가 이번 달이면 오늘까지, 지난 달 비교도 "같은 기간(1일~오늘 날짜)"으로 맞춘다. */
function computeDashboard(data, mk, today) {
  const isCurrent = mk === monthOf(today);
  const dim = daysInMonth(mk);
  const elapsed = isCurrent ? Number(today.slice(8, 10)) : dim;
  const from = monthStart(mk);
  const to = isCurrent ? today : monthEnd(mk);
  const prevMk = addMonths(mk, -1);
  const prevTo = `${prevMk}-${pad(Math.min(elapsed, daysInMonth(prevMk)))}`;
  const cats = catMap(data);

  const exp = txBetween(data, from, monthEnd(mk), 'expense');
  const inc = txBetween(data, from, monthEnd(mk), 'income');
  const expense = sumAmount(exp);
  const income = sumAmount(inc);
  const prevSame = txBetween(data, monthStart(prevMk), prevTo, 'expense');
  const prevFull = txBetween(data, monthStart(prevMk), monthEnd(prevMk), 'expense');
  const expenseToDate = sumAmount(exp.filter((t) => t.date <= to));
  const prevSameTotal = sumAmount(prevSame);

  const budget = getBudget(data, mk);
  const dailyAvg = elapsed > 0 ? expenseToDate / elapsed : 0;
  const projected = isCurrent ? Math.round(dailyAvg * dim) : expense;

  const byCatMap = new Map();
  for (const t of exp) byCatMap.set(t.category, (byCatMap.get(t.category) || 0) + t.amount);
  const prevByCat = new Map();
  for (const t of prevSame) prevByCat.set(t.category, (prevByCat.get(t.category) || 0) + t.amount);
  const allCatIds = new Set([...byCatMap.keys(), ...Object.keys(budget.byCategory || {})]);
  const byCategory = [...allCatIds].map((id) => {
    const c = cats.get(id) || getCategory(data, 'etc');
    const amount = byCatMap.get(id) || 0;
    const last = prevByCat.get(id) || 0;
    const b = (budget.byCategory || {})[id] || 0;
    return {
      id, name: c.name, icon: c.icon, color: c.color, amount,
      pct: expense > 0 ? (amount / expense) * 100 : 0,
      lastSamePeriod: last, changePct: pctChange(amount, last),
      budget: b, budgetPct: b > 0 ? (amount / b) * 100 : null,
    };
  }).sort((a, b) => b.amount - a.amount);

  const daily = dateRange(from, monthEnd(mk)).map((d) => ({ date: d, amount: sumAmount(exp.filter((t) => t.date === d)), future: d > to }));

  // 주간 비교: 이번 주(월~기준일) vs 지난주 같은 요일 구간
  const ref = isCurrent ? today : monthEnd(mk);
  const ws = weekStart(ref);
  const span = diffDays(ws, ref);
  const thisWeek = sumAmount(txBetween(data, ws, ref, 'expense'));
  const lastWeek = sumAmount(txBetween(data, addDays(ws, -7), addDays(ws, -7 + span), 'expense'));

  const merchants = new Map();
  for (const t of exp) {
    if (!t.merchant) continue;
    const k = normalizeMerchant(t.merchant);
    const m = merchants.get(k) || { name: t.merchant, count: 0, amount: 0 };
    m.count += 1; m.amount += t.amount; merchants.set(k, m);
  }
  const topMerchants = [...merchants.values()].sort((a, b) => b.count - a.count || b.amount - a.amount).slice(0, 5);
  const topTx = exp.reduce((m, t) => (!m || t.amount > m.amount ? t : m), null);

  const months = [];
  for (let i = 5; i >= 0; i -= 1) {
    const k = addMonths(mk, -i);
    months.push({ month: k, expense: sumAmount(txBetween(data, monthStart(k), monthEnd(k), 'expense')), income: sumAmount(txBetween(data, monthStart(k), monthEnd(k), 'income')) });
  }

  const allIncome = sumAmount(data.transactions.filter((t) => t.type === 'income' && t.date <= today));
  const allExpense = sumAmount(data.transactions.filter((t) => t.type === 'expense' && t.date <= today));

  return {
    month: mk, isCurrent, daysInMonth: dim, elapsed, today,
    expense, income, net: income - expense, balanceAll: allIncome - allExpense,
    count: exp.length + inc.length,
    budget: budget.total, budgetInherited: budget.inherited,
    budgetUsedPct: budget.total > 0 ? (expense / budget.total) * 100 : null,
    remaining: budget.total > 0 ? budget.total - expense : null,
    dailyAvg, projected,
    remainingPerDay: budget.total > 0 && isCurrent && dim - elapsed + 1 > 0 ? Math.max(0, (budget.total - expense) / (dim - elapsed + 1)) : null,
    prevMonth: prevMk, prevSameTotal, prevFullTotal: sumAmount(prevFull),
    changePct: pctChange(isCurrent ? expenseToDate : expense, isCurrent ? prevSameTotal : sumAmount(prevFull)),
    byCategory, daily, thisWeek, lastWeek, weekChangePct: pctChange(thisWeek, lastWeek),
    topCategory: byCategory.find((c) => c.amount > 0) || null, topTx, topMerchants, months,
    activeDays: [...activeDaySet(data, to)].filter((d) => d.startsWith(mk)).length,
  };
}

/* 앱 코드가 계산한 숫자로만 만드는 코치 메시지 (AI 없이도 동작) */
function buildInsights(data, dash, missing) {
  const out = [];
  if (!data.transactions.length) return ['첫 지출을 기록해 볼까요? 오른쪽 아래 + 버튼을 누르면 돼요.'];
  if (dash.budget > 0) {
    out.push(`이번 달 예산의 ${Math.round(dash.budgetUsedPct)}%를 사용했어요.`);
    if (dash.isCurrent && dash.projected > dash.budget && dash.elapsed >= 5) {
      out.push(`지금 속도라면 월말 예상 지출은 약 ${formatWon(dash.projected)}이에요. 예산보다 ${formatWon(dash.projected - dash.budget)} 많아요.`);
    } else if (dash.isCurrent && dash.remainingPerDay != null && dash.remaining > 0) {
      out.push(`남은 기간에는 하루 ${formatWon(dash.remainingPerDay)} 안에서 쓰면 예산을 지킬 수 있어요.`);
    }
  }
  const rising = dash.byCategory.filter((c) => c.lastSamePeriod >= 10000 && c.changePct != null && c.changePct >= 20)
    .sort((a, b) => (b.amount - b.lastSamePeriod) - (a.amount - a.lastSamePeriod))[0];
  if (rising) out.push(`이번 달 ${rising.name} 지출이 지난달 같은 기간보다 ${Math.round(rising.changePct)}% 늘었어요.`);
  const cafe = dash.byCategory.find((c) => c.id === 'cafe');
  if (cafe && cafe.amount > 0 && dash.elapsed > 0) out.push(`이번 달 카페·간식 지출은 ${formatWon(cafe.amount)}이에요. 하루 평균 약 ${formatWon(cafe.amount / dash.elapsed)}을 썼어요.`);
  for (const c of dash.byCategory) {
    if (c.budgetPct != null && c.budgetPct >= 80) {
      out.push(c.budgetPct >= 100 ? `${c.name} 예산을 넘었어요(${Math.round(c.budgetPct)}%).` : `${c.name} 예산을 ${Math.round(c.budgetPct)}% 사용했어요. 남은 기간에는 조금 줄이는 게 좋겠어요.`);
    }
  }
  const empty = missing.filter((m) => m.kind === 'empty').length;
  if (empty) out.push(`최근 기록이 없는 날이 ${empty}일 있어요. 지출이 없었다면 '지출 없음'으로 표시해 주세요.`);
  if (dash.changePct != null && dash.changePct <= -10) out.push(`지난달 같은 기간보다 지출이 ${Math.abs(Math.round(dash.changePct))}% 줄었어요. 잘하고 있어요!`);
  if (!out.length) out.push('기록이 차곡차곡 쌓이고 있어요. 오늘도 잊지 말고 남겨 주세요.');
  return out;
}

/* ---------- 캐릭터 · 미션 ----------
 * 보상은 "돈을 쓴 양"이 아니라 기록 습관(하루 1회), 예산 준수, 저축 목표 달성에만 준다. */
function computeMissions(data, today, mk = monthOf(today)) {
  const dash = computeDashboard(data, mk, today);
  const dim = daysInMonth(mk);
  const isCurrent = mk === monthOf(today);
  const noSpend = Object.entries(data.dayChecks).filter(([d, v]) => v === 'nospend' && d.startsWith(mk) && d <= today).length;
  const recordTarget = Math.min(20, dim);
  const cafeNow = (dash.byCategory.find((c) => c.id === 'cafe') || {}).amount || 0;
  const cafePrev = (dash.byCategory.find((c) => c.id === 'cafe') || {}).lastSamePeriod || 0;
  const list = [
    { id: 'record', icon: '📝', title: `이번 달 ${recordTarget}일 이상 기록하기`, progress: dash.activeDays, target: recordTarget },
    { id: 'nospend', icon: '🌙', title: '무지출 데이 4일 만들기', progress: noSpend, target: 4 },
  ];
  if (dash.budget > 0) {
    const within = dash.expense <= dash.budget;
    list.push({ id: 'budget', icon: '🎯', title: '월 예산 안에서 생활하기', progress: within ? (isCurrent ? dash.elapsed : dim) : 0, target: dim,
      note: within ? (isCurrent ? '월말까지 지키면 완료' : '완료') : '예산 초과', failed: !within });
  }
  if (cafePrev > 0) {
    list.push({ id: 'cafe', icon: '☕', title: '카페·간식 지난달보다 줄이기', progress: cafeNow < cafePrev ? 1 : 0, target: 1,
      note: `${formatWon(cafeNow)} / 지난달 같은 기간 ${formatWon(cafePrev)}`, failed: cafeNow >= cafePrev, pending: isCurrent });
  }
  return list.map((m) => ({ ...m, done: !m.failed && !m.pending && m.progress >= m.target && (m.id !== 'budget' || !isCurrent) }));
}

function computeCharacter(data, today) {
  const active = activeDaySet(data, today);
  const curMk = monthOf(today);
  const months = [...new Set([...active].map(monthOf))].filter((mk) => mk < curMk).sort();
  const keptMonths = [];
  let missionXp = 0;
  for (const mk of months) {
    const b = getBudget(data, mk);
    const days = [...active].filter((d) => d.startsWith(mk)).length;
    const exp = sumAmount(txBetween(data, monthStart(mk), monthEnd(mk), 'expense'));
    // 기록을 70% 이상 한 달만 인정 → "기록을 안 해서 예산을 지킨 것"은 보상하지 않음
    if (b.total > 0 && days / daysInMonth(mk) >= 0.7 && exp <= b.total) keptMonths.push(mk);
    missionXp += computeMissions(data, today, mk).filter((m) => m.done).length * XP_RULES.missionDone;
  }
  const achieved = data.goals.filter((g) => g.achievedAt).sort((a, b) => (a.achievedAt < b.achievedAt ? -1 : 1));
  const xp = active.size * XP_RULES.activeDay + keptMonths.length * XP_RULES.keptMonth + achieved.length * XP_RULES.goalAchieved + missionXp;
  const level = Math.floor(xp / XP_PER_LEVEL) + 1;
  let stageIdx = 0;
  STAGES.forEach((s, i) => { if (keptMonths.length >= s.min) stageIdx = i; });
  const unlocked = ITEMS.slice(0, achieved.length).map((i) => i.id);
  return {
    xp, level, levelXp: xp % XP_PER_LEVEL, levelNeed: XP_PER_LEVEL,
    stage: stageIdx, stageName: STAGES[stageIdx].name, stageDesc: STAGES[stageIdx].desc,
    nextStage: STAGES[stageIdx + 1] || null, keptMonths, activeDays: active.size,
    streak: computeStreak(data, today), unlocked, achievedGoals: achieved,
    equipped: unlocked.includes(data.character.equipped) ? data.character.equipped : null,
  };
}

function goalSaved(goal) { return goal.deposits.reduce((s, d) => s + d.amount, 0); }

/* AI에게 보낼 요약(원본 거래 대신 집계값만 → 개인정보 최소화) */
function buildAiContext(data, today) {
  const mk = monthOf(today);
  const d = computeDashboard(data, mk, today);
  const missing = detectMissing(data, today);
  const r = (n) => Math.round(n);
  return {
    today, month: mk, daysElapsed: d.elapsed, daysInMonth: d.daysInMonth,
    expense: d.expense, income: d.income, net: d.net,
    budget: d.budget || null, budgetUsedPct: d.budgetUsedPct == null ? null : r(d.budgetUsedPct),
    remainingBudget: d.remaining, dailyAvgExpense: r(d.dailyAvg), projectedMonthExpense: d.isCurrent ? d.projected : null,
    lastMonthSamePeriodExpense: d.prevSameTotal, changeVsLastMonthSamePeriodPct: d.changePct == null ? null : r(d.changePct),
    lastMonthTotalExpense: d.prevFullTotal,
    thisWeekExpense: d.thisWeek, lastWeekSamePeriodExpense: d.lastWeek,
    categories: d.byCategory.filter((c) => c.amount || c.budget).map((c) => ({
      name: c.name, amount: c.amount, sharePct: r(c.pct), lastMonthSamePeriod: c.lastSamePeriod,
      changePct: c.changePct == null ? null : r(c.changePct), budget: c.budget || null, budgetUsedPct: c.budgetPct == null ? null : r(c.budgetPct),
      dailyAvg: d.elapsed ? r(c.amount / d.elapsed) : null,
    })),
    topMerchants: d.topMerchants.map((m) => ({ name: m.name, visits: m.count, amount: m.amount })),
    biggestExpense: d.topTx ? { merchant: d.topTx.merchant, amount: d.topTx.amount, date: d.topTx.date } : null,
    recentMonths: d.months,
    daysWithoutRecordLast30: missing.filter((m) => m.kind === 'empty').map((m) => m.date),
    daysWithUnusuallyFewRecords: missing.filter((m) => m.kind === 'low').map((m) => m.date),
    recordStreakDays: computeStreak(data, today),
    savingGoals: data.goals.map((g) => ({ name: g.name, target: g.target, saved: goalSaved(g), achieved: Boolean(g.achievedAt) })),
  };
}

if (typeof module !== 'undefined') {
  module.exports = {
    STORAGE_KEY, DEFAULT_CATEGORIES, ITEMS, STAGES, XP_RULES,
    toISO, parseISO, todayISO, addDays, addMonths, monthOf, daysInMonth, isValidISO, weekStart, weekdayOf, dateRange,
    formatWon, normalizeMerchant, createEmptyData, normalizeData, normalizeTx, createStore,
    getBudget, computeStreak, detectMissing, suggestCategory, computeQuickItems, findDuplicate,
    computeDashboard, buildInsights, computeMissions, computeCharacter, goalSaved, buildAiContext,
  };
}
