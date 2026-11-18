'use strict';
/* 로컬 자연어 해석기: Gemini 없이도 "오늘 스타벅스에서 6,500원 썼어"를 해석한다.
 * 확실하지 않은 값은 uncertain에 넣어 사용자가 확인하도록 한다. */

const KO_DIGITS = { 영: 0, 공: 0, 일: 1, 이: 2, 삼: 3, 사: 4, 오: 5, 육: 6, 칠: 7, 팔: 8, 구: 9 };
const KO_SMALL = { 십: 10, 백: 100, 천: 1000 };
const KO_BIG = { 만: 1e4, 억: 1e8 };

function koreanNumber(str) {
  const s = String(str).replace(/[,\s원]/g, '');
  if (!s) return null;
  let total = 0; let section = 0; let num = null; let i = 0;
  while (i < s.length) {
    const ch = s[i];
    if (/[0-9.]/.test(ch)) {
      let j = i; while (j < s.length && /[0-9.]/.test(s[j])) j += 1;
      num = parseFloat(s.slice(i, j)); i = j; continue;
    }
    if (ch in KO_DIGITS) { num = KO_DIGITS[ch]; i += 1; continue; }
    if (ch in KO_SMALL) { section += (num ?? 1) * KO_SMALL[ch]; num = null; i += 1; continue; }
    if (ch in KO_BIG) { section += num ?? 0; total += (section || 1) * KO_BIG[ch]; section = 0; num = null; i += 1; continue; }
    return null;
  }
  total += section + (num ?? 0);
  return Number.isFinite(total) && total > 0 ? Math.round(total) : null;
}

const AMOUNT_RE = /\d[\d,]*(?:\.\d+)?(?:\s*(?:억|만|천|백)(?:\s*\d[\d,]*(?:\.\d+)?)?)*\s*(?:억|만|천|백)?\s*(원)?|[일이삼사오육칠팔구십백천만억]*[십백천만억][일이삼사오육칠팔구십백천만억]*\s*원/g;
const NOT_AMOUNT_AFTER = /^\s*(?:일|월|시|분|초|개|번|명|잔|병|권|살|년|주|박|인분|층|호|회|차|%|\/|\.)/;

function extractAmount(text) {
  const cands = [];
  AMOUNT_RE.lastIndex = 0;
  let m;
  while ((m = AMOUNT_RE.exec(text))) {
    const raw = m[0];
    if (!raw.trim()) { AMOUNT_RE.lastIndex += 1; continue; }
    const after = text.slice(m.index + raw.length);
    const before = text.slice(0, m.index);
    const hasWon = /원\s*$/.test(raw);
    if (!hasWon && (NOT_AMOUNT_AFTER.test(after) || /[/.]\s*$/.test(before))) continue;
    const value = koreanNumber(raw);
    if (!value) continue;
    cands.push({ raw, value, index: m.index, hasWon, hasUnit: /[만천억]/.test(raw) });
  }
  if (!cands.length) return null;
  cands.sort((a, b) => (b.hasWon - a.hasWon) || (b.hasUnit - a.hasUnit) || (b.value - a.value));
  return cands[0];
}

const WEEKDAY_IDX = { 일: 0, 월: 1, 화: 2, 수: 3, 목: 4, 금: 5, 토: 6 };

function extractDate(text, today) {
  const t = text;
  let m;
  if ((m = t.match(/(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?/))) {
    const iso = `${m[1]}-${String(m[2]).padStart(2, '0')}-${String(m[3]).padStart(2, '0')}`;
    if (isValidISO(iso)) return { date: iso, raw: m[0] };
  }
  if ((m = t.match(/(\d{1,2})\s*월\s*(\d{1,2})\s*일/)) || (m = t.match(/(?:^|\s)(\d{1,2})[/.](\d{1,2})(?![\d.]|\s*[만천억원])/))) {
    let y = Number(today.slice(0, 4));
    let iso = `${y}-${String(m[1]).padStart(2, '0')}-${String(m[2]).padStart(2, '0')}`;
    if (isValidISO(iso) && iso > today) { y -= 1; iso = `${y}-${iso.slice(5)}`; }
    if (isValidISO(iso)) return { date: iso, raw: m[0] };
  }
  if ((m = t.match(/(\d{1,2})\s*일\s*전/))) return { date: addDays(today, -Number(m[1])), raw: m[0] };
  if ((m = t.match(/(엊그제|그저께|그제|어제|오늘|아까|방금)/))) {
    const off = { 오늘: 0, 아까: 0, 방금: 0, 어제: -1, 그제: -2, 그저께: -2, 엊그제: -2 }[m[1]];
    return { date: addDays(today, off), raw: m[0] };
  }
  if ((m = t.match(/(지난주|저번주|저번 주|지난 주)?\s*([월화수목금토일])요일/))) {
    const target = WEEKDAY_IDX[m[2]];
    let d = today;
    if (m[1]) {
      d = addDays(weekStart(today), -7);
      while (weekdayOf(d) !== target) d = addDays(d, 1);
    } else {
      while (weekdayOf(d) !== target) d = addDays(d, -1);
    }
    return { date: d, raw: m[0] };
  }
  if ((m = t.match(/(?:^|\s)(\d{1,2})\s*일(?!\s*전)/))) {
    const day = Number(m[1]);
    let mk = monthOf(today);
    if (day > Number(today.slice(8, 10))) mk = addMonths(mk, -1);
    const iso = `${mk}-${String(day).padStart(2, '0')}`;
    if (isValidISO(iso)) return { date: iso, raw: m[0] };
  }
  return null;
}

const INCOME_RE = /(받았|받음|입금|들어왔|월급|급여|용돈 ?받|수입|환급|캐시백|이자|상여|보너스|성과급|팔았|판매)/;
const GENERIC_WORDS = ['아침', '점심', '저녁', '야식', '간식', '커피', '택시', '버스', '지하철', '장보기', '배달', '술', '회식', '밥'];
const FILLER_RE = /(에서|에다|으로|로|에|을|를|이랑|랑|하고|정도|쯤|약|총|대충|원어치)(?=\s|$)|(썼어요|썼어|썼음|씀|썼다|사용했어요|사용했어|사용|결제했어요|결제했어|결제함|결제|지출했어|지출|샀어요|샀어|샀음|구매|먹었어요|먹었어|마셨어|냈어요|냈어|냈음|탔어|했어요|했어|했음|들었어|나갔어|빠졌어|받았어요|받았어|받았음|받음|입금됨|입금|들어왔어|들어옴|팔았어)/g;

function splitEntries(text) {
  return String(text).split(/\n+|\s+그리고\s+|;|(?:,|，)\s+(?=\D)/).map((s) => s.trim()).filter(Boolean);
}

function parseNaturalOne(data, text, today) {
  const uncertain = [];
  let rest = ` ${text} `;
  const amt = extractAmount(text);
  if (amt) rest = rest.replace(amt.raw, ' ');
  const dt = extractDate(rest, today);
  if (dt) rest = rest.replace(dt.raw, ' ');
  const qty = [];
  rest = rest.replace(/\d+\s*(?:잔|개|병|인분|명|권|장|벌)/g, (q) => { qty.push(q.replace(/\s/g, '')); return ' '; });
  const type = INCOME_RE.test(text) ? 'income' : 'expense';
  const words = rest.replace(FILLER_RE, ' ').replace(/[.,!?~]/g, ' ').split(/\s+/).filter(Boolean)
    .filter((w) => !/^(나|내가|오늘|어제|그리고|좀|그냥|원|뭐|뭘|이것저것|거|것)$/.test(w));
  const specific = words.filter((w) => !GENERIC_WORDS.includes(w));
  const generic = words.filter((w) => GENERIC_WORDS.includes(w));
  const merchant = (specific.join(' ') || generic.join(' ')).slice(0, 40);
  const memo = [specific.length ? generic.join(' ') : '', qty.join(' ')].filter(Boolean).join(' ');
  const cat = suggestCategory(data, `${merchant} ${memo}`, type);
  if (!amt) uncertain.push('amount');
  if (!merchant) uncertain.push('merchant');
  return {
    date: dt ? dt.date : today,
    time: '',
    merchant,
    amount: amt ? amt.value : null,
    type,
    category: cat.id,
    memo,
    uncertain,
  };
}

function parseNatural(data, text, today) {
  return splitEntries(text).map((s) => parseNaturalOne(data, s, today));
}

if (typeof module !== 'undefined') {
  module.exports = { koreanNumber, extractAmount, extractDate, parseNatural };
}
