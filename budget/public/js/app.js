'use strict';
/* 모모 가계부 – 화면 로직. 사용자 입력은 모두 DOM 텍스트 API로만 넣는다(innerHTML 미사용). */

const store = createStore(window.localStorage);
store.load();

const state = {
  tab: 'home',
  histMonth: monthOf(todayISO()),
  histView: 'list',
  histFilter: 'all',
  statsMonth: monthOf(todayISO()),
  selected: new Set(),
  chat: [],
  ai: { available: false, model: null },
};
const today = () => todayISO();
const $ = (sel) => document.querySelector(sel);

/* ---------- DOM 헬퍼 ---------- */
function el(tag, props, ...children) {
  const node = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
      else if (k === 'value') node.value = v;
      else if (v === true) node.setAttribute(k, '');
      else node.setAttribute(k, String(v));
    }
  }
  for (const c of children.flat(Infinity)) if (c != null && c !== false) node.append(c instanceof Node ? c : String(c));
  return node;
}

/* replaceChildren은 배열·null을 처리하지 못하므로 평탄화 후 채운다 */
function fill(node, ...children) {
  node.replaceChildren(...children.flat(Infinity).filter((c) => c != null && c !== false).map((c) => (c instanceof Node ? c : String(c))));
  return node;
}

function addTo(node, ...children) {
  node.append(...children.flat(Infinity).filter((c) => c != null && c !== false).map((c) => (c instanceof Node ? c : String(c))));
  return node;
}

const ICONS = {
  home: 'M3 11l9-7 9 7v8a2 2 0 0 1-2 2h-4v-6H9v6H5a2 2 0 0 1-2-2z',
  list: 'M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01',
  chart: 'M5 20V11M11 20V5M17 20v-6M3 20h18',
  chat: 'M20 12a8 8 0 0 1-11.5 7.2L4 20l1-4.3A8 8 0 1 1 20 12z',
  heart: 'M12 20s-7.5-4.6-7.5-10.2A4.2 4.2 0 0 1 12 7.3a4.2 4.2 0 0 1 7.5 2.5C19.5 15.4 12 20 12 20z',
  gear: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4',
  mic: 'M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21',
  camera: 'M4 8h3l2-3h6l2 3h3v11H4zM12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z',
  plus: 'M12 5v14M5 12h14',
  left: 'M15 5l-7 7 7 7',
  right: 'M9 5l7 7-7 7',
  close: 'M6 6l12 12M18 6L6 18',
  pen: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4',
  calendar: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4',
  send: 'M4 12l16-8-6 16-2-7z',
};
function icon(name, size = 22) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('width', size); s.setAttribute('height', size);
  s.setAttribute('aria-hidden', 'true'); s.setAttribute('class', 'ico');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', ICONS[name]);
  s.append(p);
  return s;
}

function amountInput(value, attrs = {}) {
  const input = el('input', { type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: '0', ...attrs });
  input.value = value ? Number(value).toLocaleString('ko-KR') : '';
  input.addEventListener('input', () => {
    const digits = input.value.replace(/[^\d]/g, '').replace(/^0+/, '').slice(0, 11);
    input.value = digits ? Number(digits).toLocaleString('ko-KR') : '';
  });
  return input;
}
const readAmount = (input) => Number(String(input.value).replace(/[^\d]/g, '')) || 0;

function categorySelect(type, value, attrs = {}) {
  return el('select', attrs, store.data.categories.filter((c) => c.type === type)
    .map((c) => el('option', { value: c.id, selected: c.id === value }, `${c.icon} ${c.name}`)));
}

function progressBar(pct, { warn = 80, label } = {}) {
  const p = Math.max(0, Math.min(100, pct || 0));
  const cls = pct >= 100 ? 'over' : pct >= warn ? 'warn' : '';
  return el('div', { class: `progress ${cls}`, role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(p), 'aria-label': label || '진행률' },
    el('span', { style: { width: `${p}%` } }));
}

function monthNav(mk, onChange) {
  const isMax = mk >= monthOf(today());
  return el('div', { class: 'month-nav' },
    el('button', { type: 'button', class: 'icon-btn', 'aria-label': '이전 달', onclick: () => onChange(addMonths(mk, -1)) }, icon('left')),
    el('strong', {}, monthLabel(mk)),
    el('button', { type: 'button', class: 'icon-btn', 'aria-label': '다음 달', disabled: isMax, onclick: () => onChange(addMonths(mk, 1)) }, icon('right')));
}

function segmented(options, value, onChange, label) {
  return el('div', { class: 'segmented', role: 'group', 'aria-label': label },
    options.map(([v, text]) => el('button', { type: 'button', 'aria-pressed': String(v === value), onclick: () => onChange(v) }, text)));
}

/* ---------- 토스트 ---------- */
const toastBox = document.getElementById('toast');
let toastTimer = null;
function toast(message, undo) {
  const box = toastBox;
  const host = sheet.open ? sheet : document.body; // 열린 dialog(top layer) 위에서도 보이도록
  if (box.parentNode !== host) host.append(box);
  fill(box, el('span', {}, message), undo ? el('button', { type: 'button', onclick: () => { box.classList.remove('show'); undo(); } }, '되돌리기') : null);
  box.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove('show'), undo ? 6000 : 3000);
}

/* ---------- 바텀시트 ---------- */
const sheet = $('#sheet');
function openSheet(title, body, footer) {
  fill(sheet, el('div', { class: 'sheet-inner' },
    el('div', { class: 'sheet-grip', 'aria-hidden': 'true' }),
    el('div', { class: 'sheet-head' }, el('h2', { id: 'sheet-title' }, title),
      el('button', { type: 'button', class: 'icon-btn', 'aria-label': '닫기', onclick: closeSheet }, icon('close'))),
    el('div', { class: 'sheet-body' }, body),
    footer ? el('div', { class: 'sheet-foot' }, footer) : null));
  if (!sheet.open) sheet.showModal();
}
function closeSheet() { if (sheet.open) sheet.close(); }
sheet.addEventListener('click', (e) => { if (e.target === sheet) closeSheet(); });
sheet.addEventListener('close', () => { stopVoice(); render(); });

/* ---------- 저장 ---------- */
function persist() {
  if (!store.save()) { toast('저장하지 못했어요. 저장 공간을 확인하고 백업해 주세요.'); return false; }
  return true;
}
function addTransactions(items, source) {
  const now = new Date().toISOString();
  const added = items.map((i) => normalizeTx({ ...i, id: uid(), source, createdAt: now, updatedAt: now })).filter(Boolean);
  store.data.transactions.push(...added);
  for (const t of added) {
    if (store.data.dayChecks[t.date] === 'nospend' && t.type === 'expense') delete store.data.dayChecks[t.date];
  }
  persist();
  return added;
}
function undoAdd(ids) {
  return () => {
    store.data.transactions = store.data.transactions.filter((t) => !ids.includes(t.id));
    persist(); render(); toast('입력을 취소했어요.');
  };
}
function txTitle(t) { return t.merchant || getCategory(store.data, t.category).name; }

/* ---------- AI 서버 ---------- */
async function api(path, body) {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'AI 요청이 실패했어요.');
  return data;
}
async function checkAi() {
  if (!/^https?:$/.test(location.protocol)) return;
  try {
    const res = await fetch('/api/status');
    if (res.ok) { const s = await res.json(); state.ai = { available: Boolean(s.ai), model: s.model }; render(); }
  } catch { /* 오프라인 → 로컬 기능만 */ }
}
const categoryPayload = () => store.data.categories.map((c) => ({ id: c.id, name: c.name, type: c.type }));

/* ---------- 음성 입력 (브라우저 Web Speech API) ---------- */
const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
function stopVoice() { if (recognizer) { try { recognizer.stop(); } catch { /* noop */ } recognizer = null; } }

/* ======================================================================
 * 입력 시트: 직접 입력 / 말로 입력 / 캡처로 입력
 * ==================================================================== */
function openEntry(opts = {}) {
  const editing = opts.tx || null;
  let mode = editing ? 'manual' : opts.mode || 'manual';
  const wrap = el('div', { class: 'entry' });
  const draw = () => {
    stopVoice();
    const tabs = editing ? null : segmented([['manual', '직접 입력'], ['nl', '말로 입력'], ['image', '캡처로 입력']], mode, (m) => { mode = m; draw(); }, '입력 방식');
    const panel = mode === 'manual' ? manualPanel(editing, opts) : mode === 'nl' ? nlPanel(opts) : imagePanel();
    fill(wrap, tabs, panel);
  };
  openSheet(editing ? '기록 수정' : '기록하기', wrap);
  draw();
}

function manualPanel(editing, opts) {
  const f = {
    type: editing ? editing.type : opts.type || 'expense',
    category: editing ? editing.category : null,
    date: editing ? editing.date : opts.date || today(),
  };
  let catTouched = Boolean(editing);
  const form = el('form', { class: 'manual', novalidate: true });
  const amount = amountInput(editing && editing.amount, { id: 'f-amount', 'aria-label': '금액', class: 'amount-input', enterkeyhint: 'done' });
  const merchant = el('input', { id: 'f-merchant', type: 'text', maxlength: 60, placeholder: '어디에서? (예: 스타벅스)', autocomplete: 'off', value: editing ? editing.merchant : '' });
  const memo = el('input', { id: 'f-memo', type: 'text', maxlength: 200, placeholder: '메모 (선택)', value: editing ? editing.memo : '' });
  const dateInput = el('input', { id: 'f-date', type: 'date', value: f.date, 'aria-label': '날짜 직접 선택' });
  const hint = el('p', { class: 'hint', 'aria-live': 'polite' });
  const grid = el('div', { class: 'cat-grid', role: 'group', 'aria-label': '카테고리' });
  const typeBox = el('div');
  const dateChips = el('div', { class: 'chips', role: 'group', 'aria-label': '빠른 날짜' });

  function drawType() {
    fill(typeBox, segmented([['expense', '지출'], ['income', '수입']], f.type, (t) => {
      f.type = t; f.category = null; catTouched = false; drawType(); suggest(); drawGrid();
    }, '거래 유형'));
  }
  function drawGrid() {
    const cats = store.data.categories.filter((c) => c.type === f.type);
    if (!f.category || !cats.some((c) => c.id === f.category)) f.category = cats.find((c) => c.id === (f.type === 'income' ? 'salary' : 'food'))?.id || cats[0].id;
    fill(grid, ...cats.map((c) => el('button', {
      type: 'button', class: 'cat', 'aria-pressed': String(c.id === f.category), style: { '--c': c.color },
      onclick: () => { f.category = c.id; catTouched = true; hint.textContent = ''; drawGrid(); },
    }, el('span', { class: 'cat-ico', 'aria-hidden': 'true' }, c.icon), el('span', {}, c.name))));
  }
  function suggest() {
    if (catTouched) return;
    const text = `${merchant.value} ${memo.value}`.trim();
    if (!text) { hint.textContent = ''; return; }
    const s = suggestCategory(store.data, text, f.type);
    if (s.reason === 'default') { hint.textContent = ''; return; }
    f.category = s.id;
    const c = getCategory(store.data, s.id);
    hint.textContent = `${c.icon} ${c.name} 추천 · ${s.reason === 'history' ? '지난 기록 기준' : '사용처 이름 기준'}`;
    drawGrid();
  }
  function drawDates() {
    const t = today();
    fill(dateChips, ...[['오늘', t], ['어제', addDays(t, -1)], ['그제', addDays(t, -2)]].map(([label, d]) => el('button', {
      type: 'button', class: 'chip', 'aria-pressed': String(dateInput.value === d), onclick: () => { dateInput.value = d; drawDates(); },
    }, label)), dateInput);
  }
  merchant.addEventListener('input', suggest);
  memo.addEventListener('input', suggest);
  dateInput.addEventListener('change', drawDates);

  const addChips = el('div', { class: 'chips small' }, [1000, 5000, 10000, 50000].map((n) => el('button', {
    type: 'button', class: 'chip', onclick: () => { amount.value = (readAmount(amount) + n).toLocaleString('ko-KR'); amount.focus(); },
  }, `+${shortWon(n)}`)), el('button', { type: 'button', class: 'chip ghost', onclick: () => { amount.value = ''; amount.focus(); } }, '지우기'));

  // 자주 쓰는 지출: 한 번 탭하면 오늘 날짜로 바로 저장(되돌리기 가능)
  const quick = editing ? [] : computeQuickItems(store.data, today());
  const quickRow = quick.length && f.type === 'expense' ? el('div', { class: 'quick' },
    el('p', { class: 'label' }, '자주 쓰는 지출 · 탭하면 바로 기록'),
    el('div', { class: 'chips scroll' }, quick.map((q) => el('button', {
      type: 'button', class: 'chip quick-chip', onclick: () => {
        const added = addTransactions([{ date: today(), type: 'expense', amount: q.amount, category: q.category, merchant: q.merchant }], 'quick');
        closeSheet(); toast(`${q.merchant} ${formatWon(q.amount)} 기록했어요`, undoAdd(added.map((t) => t.id)));
      },
    }, `${getCategory(store.data, q.category).icon} ${q.merchant} ${formatWon(q.amount)}`)))) : null;

  const errorBox = el('p', { class: 'error', role: 'alert' });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const value = readAmount(amount);
    if (!value) { errorBox.textContent = '금액을 입력해 주세요.'; amount.focus(); return; }
    if (!isValidISO(dateInput.value)) { errorBox.textContent = '날짜를 확인해 주세요.'; dateInput.focus(); return; }
    const payload = { date: dateInput.value, type: f.type, amount: value, category: f.category, merchant: merchant.value.trim(), memo: memo.value.trim() };
    if (editing) {
      const idx = store.data.transactions.findIndex((t) => t.id === editing.id);
      const before = { ...store.data.transactions[idx] };
      store.data.transactions[idx] = normalizeTx({ ...before, ...payload, updatedAt: new Date().toISOString() });
      persist(); closeSheet();
      toast('수정했어요', () => { const i = store.data.transactions.findIndex((t) => t.id === before.id); if (i >= 0) store.data.transactions[i] = before; persist(); render(); });
    } else {
      const added = addTransactions([payload], 'manual');
      closeSheet();
      toast(`${txTitle(added[0])} ${formatWon(value)} 기록했어요`, undoAdd(added.map((t) => t.id)));
    }
  });

  const del = editing ? el('button', {
    type: 'button', class: 'btn danger-ghost', onclick: () => {
      const removed = store.data.transactions.find((t) => t.id === editing.id);
      store.data.transactions = store.data.transactions.filter((t) => t.id !== editing.id);
      persist(); closeSheet();
      toast('삭제했어요', () => { store.data.transactions.push(removed); persist(); render(); });
    },
  }, '삭제') : null;

  drawType(); drawGrid(); drawDates();
  addTo(form,
    typeBox,
    el('label', { class: 'amount-field', for: 'f-amount' }, amount, el('span', { 'aria-hidden': 'true' }, '원')),
    addChips, quickRow,
    el('label', { class: 'label', for: 'f-merchant' }, '사용처'), merchant, hint,
    grid,
    el('p', { class: 'label' }, '날짜'), dateChips,
    el('label', { class: 'label', for: 'f-memo' }, '메모'), memo,
    errorBox,
    el('div', { class: 'form-actions' }, del, el('button', { type: 'submit', class: 'btn primary grow' }, editing ? '수정 완료' : '저장')),
  );
  setTimeout(() => { if (!editing) amount.focus(); }, 60);
  return form;
}

function nlPanel(opts = {}) {
  const box = el('div', { class: 'nl' });
  const area = el('textarea', { id: 'nl-text', rows: 3, maxlength: 1000, placeholder: '예) 오늘 스타벅스에서 6,500원 썼어\n어제 점심 김밥천국 8000원 그리고 택시 1만 2천원' });
  area.value = opts.text || '';
  const result = el('div', { class: 'preview-wrap' });
  const status = el('p', { class: 'hint', 'aria-live': 'polite' });
  let usedVoice = false;

  const mic = SpeechRec ? el('button', { type: 'button', class: 'btn soft', 'aria-pressed': 'false', onclick: () => {
    if (recognizer) { stopVoice(); mic.setAttribute('aria-pressed', 'false'); status.textContent = ''; return; }
    recognizer = new SpeechRec();
    recognizer.lang = 'ko-KR'; recognizer.interimResults = true; recognizer.continuous = false;
    const base = area.value ? `${area.value}\n` : '';
    recognizer.onresult = (ev) => { area.value = base + [...ev.results].map((r) => r[0].transcript).join(' '); usedVoice = true; };
    recognizer.onerror = (ev) => { status.textContent = ev.error === 'not-allowed' ? '마이크 권한이 필요해요.' : '음성을 듣지 못했어요. 다시 시도해 주세요.'; };
    recognizer.onend = () => { recognizer = null; mic.setAttribute('aria-pressed', 'false'); if (area.value.trim()) run(); };
    recognizer.start();
    mic.setAttribute('aria-pressed', 'true');
    status.textContent = '듣고 있어요… 말을 마치면 자동으로 해석해요.';
  } }, icon('mic', 18), '말하기') : null;

  async function run() {
    const text = area.value.trim();
    if (!text) { status.textContent = '내용을 입력해 주세요.'; area.focus(); return; }
    let items; let by = '로컬 해석';
    status.textContent = '해석하는 중…';
    if (state.ai.available) {
      try { items = (await api('/api/parse', { text, today: today(), categories: categoryPayload() })).items; by = 'Gemini'; }
      catch (e) { status.textContent = `${e.message} 로컬 해석기로 대신 처리했어요.`; }
    }
    if (!items) items = parseNatural(store.data, text, today());
    if (!items.length) { status.textContent = '거래를 찾지 못했어요. 금액을 포함해서 다시 적어 주세요.'; return; }
    if (status.textContent === '해석하는 중…') status.textContent = `${by}로 ${items.length}건을 찾았어요. 확인 후 저장해 주세요.`;
    renderPreview(result, items, { source: usedVoice ? 'voice' : 'nl', onSaved: closeSheet });
  }

  addTo(box,
    el('label', { class: 'label', for: 'nl-text' }, '평소 말하듯 적어 주세요'),
    area,
    el('div', { class: 'row gap' }, mic, el('button', { type: 'button', class: 'btn primary grow', onclick: run }, '해석하기')),
    status,
    el('p', { class: 'fine' }, state.ai.available ? 'AI가 해석하지만, 저장은 내용을 확인한 뒤에만 돼요.' : 'AI 서버 없이 앱 안의 해석기로 처리해요. 저장 전에 꼭 확인해 주세요.'),
    result,
  );
  if (opts.text) setTimeout(run, 0);
  return box;
}

function imagePanel() {
  const box = el('div', { class: 'image-entry' });
  if (!state.ai.available) {
    addTo(box, el('div', { class: 'empty-msg' },
      el('p', {}, '캡처 인식은 AI 서버(Gemini)가 연결되어야 쓸 수 있어요.'),
      el('p', { class: 'fine' }, '서버에 GEMINI_API_KEY를 설정하고 node server.js로 실행해 주세요. 그동안은 직접 입력이나 말로 입력을 이용해 주세요.')));
    return box;
  }
  const result = el('div', { class: 'preview-wrap' });
  const status = el('p', { class: 'hint', 'aria-live': 'polite' });
  const file = el('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp', id: 'img-file', class: 'visually-hidden' });
  file.addEventListener('change', async () => {
    const f = file.files && file.files[0];
    if (!f) return;
    fill(result);
    status.textContent = '모모가 거래내역을 읽고 있어요… (10~30초)';
    const upload = { id: uid(), createdAt: new Date().toISOString(), fileName: f.name.slice(0, 60), found: 0, saved: 0 };
    try {
      const image = await imageToBase64(f);
      const { items } = await api('/api/ocr', { image, mimeType: 'image/jpeg', today: today(), categories: categoryPayload() });
      upload.found = items.length;
      store.data.uploads.push(upload); persist();
      if (!items.length) { status.textContent = '이미지에서 거래를 찾지 못했어요. 거래 목록이 잘 보이게 다시 캡처해 주세요.'; return; }
      const unsure = items.filter((i) => i.uncertain.includes('amount') || i.uncertain.includes('date')).length;
      status.textContent = `${items.length}건을 찾았어요.${unsure ? ` 그중 ${unsure}건은 금액이나 날짜 확인이 필요해요.` : ''}`;
      renderPreview(result, items, { source: 'image', onSaved: (n) => { const u = store.data.uploads.find((x) => x.id === upload.id); if (u) { u.saved = n; persist(); } closeSheet(); } });
    } catch (e) {
      status.textContent = e.message || '이미지를 처리하지 못했어요.';
    } finally { file.value = ''; }
  });
  addTo(box,
    el('label', { class: 'upload-drop', for: 'img-file' }, icon('camera', 30), el('strong', {}, '거래내역 캡처 올리기'), el('span', { class: 'fine' }, '은행·카드 앱 화면 캡처 (여러 건 OK)')),
    file, status,
    el('p', { class: 'fine' }, '이미지는 분석에만 쓰이고 서버·기기에 저장하지 않아요. 계좌번호 등 민감한 부분은 가리고 올려도 돼요. Gemini 무료 등급은 Google 약관에 따라 입력 데이터가 서비스 개선에 쓰일 수 있어요.'),
    result,
  );
  return box;
}

async function imageToBase64(file) {
  if (!/^image\//.test(file.type)) throw new Error('이미지 파일만 올릴 수 있어요.');
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image(); i.onload = () => resolve(i); i.onerror = () => reject(new Error('이미지를 열지 못했어요.')); i.src = url;
    });
    const scale = Math.min(1, 2000 / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement('canvas');
    c.width = Math.round(img.naturalWidth * scale); c.height = Math.round(img.naturalHeight * scale);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.9).split(',')[1];
  } finally { URL.revokeObjectURL(url); }
}

/* 저장 전 미리보기: 불확실한 금액·날짜는 사용자가 확인해야만 저장, 중복 후보는 기본 해제 */
function renderPreview(container, rawItems, { source, onSaved }) {
  const items = rawItems.map((it) => {
    const type = it.type === 'income' ? 'income' : 'expense';
    const cat = it.category && store.data.categories.some((c) => c.id === it.category && c.type === type) ? it.category : suggestCategory(store.data, it.merchant, type).id;
    const item = { ...it, type, category: cat, uncertain: new Set(it.uncertain || []) };
    item.dup = findDuplicate(store.data, item);
    item.include = !item.dup;
    return item;
  });
  const needsConfirm = (it) => it.uncertain.has('amount') || it.uncertain.has('date');
  const valid = (it) => it.amount > 0 && isValidISO(it.date || '') && !needsConfirm(it);
  const saveBtn = el('button', { type: 'button', class: 'btn primary grow' });

  function refreshSave() {
    const n = items.filter((i) => i.include && valid(i)).length;
    saveBtn.textContent = n ? `${n}건 저장` : '저장할 항목을 확인해 주세요';
    saveBtn.disabled = !n;
  }

  function card(it) {
    const node = el('div', { class: 'pv-card' });
    const draw = () => {
      it.dup = findDuplicate(store.data, it);
      const ok = valid(it);
      if (!ok) it.include = false;
      const flag = (field) => (it.uncertain.has(field) ? 'needs-check' : '');
      const check = el('input', { type: 'checkbox', checked: it.include && ok, disabled: !ok, 'aria-label': '이 거래 저장' });
      check.addEventListener('change', () => { it.include = check.checked; refreshSave(); });
      const date = el('input', { type: 'date', value: it.date || '', class: flag('date'), 'aria-label': '날짜' });
      date.addEventListener('change', () => { it.date = date.value || null; it.uncertain.delete('date'); it.include = true; draw(); refreshSave(); });
      const amt = amountInput(it.amount, { class: flag('amount'), 'aria-label': '금액' });
      amt.addEventListener('change', () => { it.amount = readAmount(amt) || null; it.uncertain.delete('amount'); it.include = true; draw(); refreshSave(); });
      const mer = el('input', { type: 'text', value: it.merchant || '', maxlength: 60, placeholder: '사용처', class: flag('merchant'), 'aria-label': '사용처' });
      mer.addEventListener('change', () => { it.merchant = mer.value.trim(); it.uncertain.delete('merchant'); draw(); refreshSave(); });
      const cat = categorySelect(it.type, it.category, { class: flag('category'), 'aria-label': '카테고리' });
      cat.addEventListener('change', () => { it.category = cat.value; it.uncertain.delete('category'); });
      const type = el('select', { class: flag('type'), 'aria-label': '유형' }, el('option', { value: 'expense', selected: it.type === 'expense' }, '지출'), el('option', { value: 'income', selected: it.type === 'income' }, '수입'));
      type.addEventListener('change', () => {
        it.type = type.value; it.uncertain.delete('type');
        it.category = suggestCategory(store.data, it.merchant, it.type).id; draw(); refreshSave();
      });
      const notes = [];
      if (needsConfirm(it)) {
        notes.push(el('div', { class: 'pv-note warn' }, el('span', {}, `${[it.uncertain.has('amount') && '금액', it.uncertain.has('date') && '날짜'].filter(Boolean).join('·')}이 확실하지 않아요. 확인하거나 고쳐 주세요.`),
          it.amount > 0 && isValidISO(it.date || '') ? el('button', { type: 'button', class: 'chip', onclick: () => { it.uncertain.delete('amount'); it.uncertain.delete('date'); it.include = true; draw(); refreshSave(); } }, '맞아요') : null));
      }
      if (it.dup) notes.push(el('div', { class: 'pv-note dup' }, `이미 등록된 거래와 같아 보여요: ${dayLabel(it.dup.date)} ${txTitle(it.dup)} ${formatWon(it.dup.amount)}`));
      if (it.uncertain.has('type')) notes.push(el('div', { class: 'pv-note warn' }, '지출/수입 구분을 확인해 주세요.'));
      if (it.memo) notes.push(el('div', { class: 'fine' }, `메모: ${it.memo}`));
      fill(node, 
        el('label', { class: 'pv-check' }, check, el('span', {}, it.time ? `${it.time}` : '저장')),
        el('div', { class: 'pv-fields' }, el('div', { class: 'row gap' }, date, amt), el('div', { class: 'row gap' }, mer, type), cat, notes),
      );
    };
    draw();
    return node;
  }

  saveBtn.addEventListener('click', () => {
    const chosen = items.filter((i) => i.include && valid(i));
    if (!chosen.length) return;
    const added = addTransactions(chosen.map(({ date, time, type, amount, category, merchant, memo }) => ({ date, time, type, amount, category, merchant, memo })), source);
    onSaved && onSaved(added.length);
    toast(`${added.length}건 기록했어요`, undoAdd(added.map((t) => t.id)));
  });

  fill(container, 
    el('div', { class: 'pv-list' }, items.map(card)),
    el('div', { class: 'sticky-actions' }, saveBtn),
  );
  refreshSave();
}

/* ======================================================================
 * 홈
 * ==================================================================== */
function renderHome(t) {
  const d = store.data;
  const dash = computeDashboard(d, monthOf(t), t);
  const missing = detectMissing(d, t, 14);
  const insights = buildInsights(d, dash, missing);
  const ch = computeCharacter(d, t);
  const mood = dash.budgetUsedPct != null && dash.budgetUsedPct >= 90 ? 'worry' : 'happy';
  const empties = missing.filter((m) => m.kind === 'empty');

  const coach = el('section', { class: 'card coach' },
    el('div', { class: 'coach-mascot' }, mascotSvg({ stage: ch.stage, item: ch.equipped, mood, size: 76 })),
    el('div', { class: 'bubble' },
      el('p', {}, insights[0]),
      insights.length > 1 ? el('button', { type: 'button', class: 'link', onclick: () => setTab('ai') }, `모모의 분석 ${insights.length - 1}개 더 보기`) : null));

  const budgetBlock = dash.budget > 0
    ? [el('div', { class: 'row between' }, el('span', { class: 'muted' }, dash.remaining >= 0 ? '남은 예산' : '예산 초과'),
      el('strong', { class: dash.remaining >= 0 ? '' : 'neg' }, formatWon(Math.abs(dash.remaining)))),
    progressBar(dash.budgetUsedPct, { label: '예산 사용률' }),
    el('p', { class: 'fine' }, `예산 ${formatWon(dash.budget)} 중 ${Math.round(dash.budgetUsedPct)}% 사용${dash.remainingPerDay != null && dash.remaining > 0 ? ` · 하루 ${formatWon(dash.remainingPerDay)}씩 쓸 수 있어요` : ''}`)]
    : el('button', { type: 'button', class: 'btn soft small', onclick: openSettings }, '이번 달 예산 정하기');

  const summary = el('section', { class: 'card hero' },
    el('p', { class: 'muted' }, `${Number(t.slice(5, 7))}월 지출`),
    el('p', { class: 'big-num' }, formatWon(dash.expense)),
    dash.changePct != null ? el('p', { class: 'fine' }, `지난달 같은 기간보다 ${formatPct(dash.changePct)}`) : null,
    budgetBlock,
    el('div', { class: 'mini-grid' },
      el('div', {}, el('span', { class: 'muted' }, '이번 달 수입'), el('strong', { class: 'pos' }, formatWon(dash.income))),
      el('div', {}, el('span', { class: 'muted' }, '누적 잔액'), el('strong', {}, formatWon(dash.balanceAll)))));

  const recovery = empties.length ? el('section', { class: 'card recover' },
    el('div', {}, el('strong', {}, `최근 2주 중 ${empties.length}일이 비어 있어요`),
      el('p', { class: 'fine' }, '지출이 없던 날이면 "지출 없음"만 눌러도 돼요.')),
    el('button', { type: 'button', class: 'btn soft small', onclick: () => {
      state.tab = 'history'; state.histView = 'calendar'; state.histMonth = monthOf(t);
      state.selected = new Set(empties.map((m) => m.date)); render(); window.scrollTo(0, 0);
    } }, '채우러 가기')) : null;

  const quick = computeQuickItems(d, t, 4);
  const inputCard = el('section', { class: 'card input-card' },
    el('button', { type: 'button', class: 'btn primary big', onclick: () => openEntry() }, icon('plus', 20), '지출 기록하기'),
    el('div', { class: 'row gap' },
      el('button', { type: 'button', class: 'btn soft grow', onclick: () => openEntry({ mode: 'nl' }) }, icon('mic', 18), '말로'),
      el('button', { type: 'button', class: 'btn soft grow', onclick: () => openEntry({ mode: 'image' }) }, icon('camera', 18), '캡처로'),
      el('button', { type: 'button', class: 'btn soft grow', onclick: () => openEntry({ type: 'income' }) }, '수입')),
    quick.length ? el('div', { class: 'chips scroll' }, quick.map((q) => el('button', { type: 'button', class: 'chip quick-chip', onclick: () => {
      const added = addTransactions([{ date: t, type: 'expense', amount: q.amount, category: q.category, merchant: q.merchant }], 'quick');
      render(); toast(`${q.merchant} ${formatWon(q.amount)} 기록했어요`, undoAdd(added.map((x) => x.id)));
    } }, `${getCategory(d, q.category).icon} ${q.merchant} ${formatWon(q.amount)}`))) : null);

  const cats = dash.byCategory.filter((c) => c.amount > 0);
  const chart = cats.length ? el('section', { class: 'card' },
    el('div', { class: 'row between' }, el('h3', {}, '어디에 썼을까'), el('button', { type: 'button', class: 'link', onclick: () => setTab('stats') }, '통계 보기')),
    el('div', { class: 'donut-row' },
      donutChart(cats.slice(0, 6).map((c) => ({ value: c.amount, color: c.color, label: c.name })), { size: 132, thickness: 20, title: `${cats.length}개`, subtitle: '카테고리' }),
      el('ul', { class: 'legend' }, cats.slice(0, 4).map((c) => el('li', {}, el('i', { style: { background: c.color } }), `${c.icon} ${c.name}`, el('b', {}, `${Math.round(c.pct)}%`)))))) : null;

  const recent = [...d.transactions].sort((a, b) => (a.date === b.date ? (a.createdAt < b.createdAt ? 1 : -1) : a.date < b.date ? 1 : -1)).slice(0, 5);
  const recentCard = el('section', { class: 'card' },
    el('div', { class: 'row between' }, el('h3', {}, '최근 기록'), recent.length ? el('button', { type: 'button', class: 'link', onclick: () => setTab('history') }, '전체 보기') : null),
    recent.length ? el('ul', { class: 'tx-list' }, recent.map((x) => txRow(x, true))) : el('p', { class: 'empty-msg' }, '아직 기록이 없어요. 첫 지출을 남겨 볼까요?'));

  const needBackup = d.transactions.length >= 20 && (!d.meta.lastBackupAt || diffDays(d.meta.lastBackupAt.slice(0, 10), t) > 30);
  const backup = needBackup ? el('section', { class: 'card note' },
    el('p', {}, '기록이 이 기기 브라우저에만 저장돼요. 한 달에 한 번 백업 파일을 받아 두면 안전해요.'),
    el('button', { type: 'button', class: 'btn soft small', onclick: downloadBackup }, '백업 받기')) : null;

  return el('div', { class: 'stack' }, coach, summary, recovery, inputCard, chart, recentCard, backup);
}

function txRow(t, showDate = false) {
  const c = getCategory(store.data, t.category);
  const sub = [showDate ? dayLabel(t.date) : null, c.name, t.time || null, t.memo || null].filter(Boolean).join(' · ');
  return el('li', {}, el('button', { type: 'button', class: 'tx', onclick: () => openEntry({ tx: t }), 'aria-label': `${txTitle(t)} ${formatWon(t.amount)} 수정` },
    el('span', { class: 'tx-ico', style: { background: c.color }, 'aria-hidden': 'true' }, c.icon),
    el('span', { class: 'tx-main' }, el('span', { class: 'tx-title' }, txTitle(t)), el('span', { class: 'tx-sub' }, sub)),
    el('span', { class: `tx-amt ${t.type === 'income' ? 'pos' : ''}` }, `${t.type === 'income' ? '+' : '-'}${formatWon(t.amount)}`)));
}

/* ======================================================================
 * 거래내역 + 달력(누락 복구)
 * ==================================================================== */
function renderHistory(t) {
  const mk = state.histMonth;
  const head = el('div', { class: 'stack tight' },
    monthNav(mk, (m) => { state.histMonth = m; render(); }),
    segmented([['list', '목록'], ['calendar', '달력 · 빠진 날 채우기']], state.histView, (v) => { state.histView = v; render(); }, '보기 방식'));
  return el('div', { class: 'stack' }, head, state.histView === 'list' ? historyList(mk) : historyCalendar(mk, t));
}

function historyList(mk) {
  const d = store.data;
  const monthTx = d.transactions.filter((x) => x.date.startsWith(mk));
  const usedCats = [...new Set(monthTx.map((x) => x.category))].map((id) => getCategory(d, id));
  const filter = state.histFilter;
  const list = monthTx.filter((x) => filter === 'all' || (filter === 'income' ? x.type === 'income' : x.category === filter))
    .sort((a, b) => (a.date === b.date ? (a.createdAt < b.createdAt ? 1 : -1) : a.date < b.date ? 1 : -1));
  const chips = el('div', { class: 'chips scroll', role: 'group', 'aria-label': '카테고리 필터' },
    [['all', '전체'], ['income', '수입'], ...usedCats.filter((c) => c.type === 'expense').map((c) => [c.id, `${c.icon} ${c.name}`])]
      .map(([v, label]) => el('button', { type: 'button', class: 'chip', 'aria-pressed': String(filter === v), onclick: () => { state.histFilter = v; render(); } }, label)));
  const exp = sumAmount(list.filter((x) => x.type === 'expense'));
  const inc = sumAmount(list.filter((x) => x.type === 'income'));
  const groups = new Map();
  for (const x of list) { if (!groups.has(x.date)) groups.set(x.date, []); groups.get(x.date).push(x); }
  const body = list.length
    ? [...groups.entries()].map(([date, txs]) => el('section', { class: 'day-group' },
      el('div', { class: 'day-head' }, el('span', {}, dayLabel(date)), el('span', { class: 'muted' }, `-${formatWon(sumAmount(txs.filter((x) => x.type === 'expense')))}`)),
      el('ul', { class: 'tx-list' }, txs.map((x) => txRow(x)))))
    : el('p', { class: 'empty-msg' }, monthTx.length ? '이 조건의 기록이 없어요.' : '이 달에는 기록이 없어요. 달력에서 빠진 날을 채워 보세요.');
  return el('div', { class: 'stack' }, chips,
    el('div', { class: 'card row between slim' }, el('span', {}, `지출 ${formatWon(exp)}`), el('span', { class: 'pos' }, `수입 ${formatWon(inc)}`)),
    body);
}

function historyCalendar(mk, t) {
  const d = store.data;
  const first = d.transactions.reduce((m, x) => (x.date < m ? x.date : m), t);
  const lows = new Map(detectMissing(d, t, 400).filter((m) => m.kind === 'low').map((m) => [m.date, m]));
  const byDay = new Map();
  for (const x of d.transactions) {
    if (!x.date.startsWith(mk)) continue;
    const v = byDay.get(x.date) || { exp: 0, n: 0 };
    if (x.type === 'expense') v.exp += x.amount;
    v.n += 1; byDay.set(x.date, v);
  }
  const days = dateRange(`${mk}-01`, `${mk}-${String(daysInMonth(mk)).padStart(2, '0')}`);
  const status = (day) => {
    if (day > t) return 'future';
    if (d.dayChecks[day] === 'nospend') return 'nospend';
    if (byDay.has(day)) return lows.has(day) ? 'low' : 'recorded';
    if (day === t || !d.transactions.length || day < first || d.dayChecks[day]) return 'blank';
    return 'empty';
  };
  const emptyDays = days.filter((x) => status(x) === 'empty');
  const lowDays = days.filter((x) => status(x) === 'low');

  const grid = el('div', { class: 'cal', role: 'grid', 'aria-label': `${monthLabel(mk)} 달력` },
    WEEKDAYS.map((w) => el('div', { class: 'cal-w', role: 'columnheader' }, w)),
    Array.from({ length: parseISO(days[0]).getDay() }, () => el('div', { 'aria-hidden': 'true' })),
    days.map((day) => {
      const s = status(day);
      const v = byDay.get(day);
      const sel = state.selected.has(day);
      const desc = { future: '', nospend: '지출 없음', recorded: '기록 있음', low: '기록이 평소보다 적음', blank: '', empty: '기록 없음' }[s];
      return el('button', {
        type: 'button', class: `cal-d ${s}${sel ? ' sel' : ''}${day === t ? ' today' : ''}`, disabled: s === 'future',
        'aria-pressed': String(sel), 'aria-label': `${dayLabel(day)} ${desc}${v && v.exp ? ` 지출 ${formatWon(v.exp)}` : ''}`,
        onclick: () => { if (sel) state.selected.delete(day); else state.selected.add(day); render(); },
      }, el('span', { class: 'n' }, Number(day.slice(8))), el('span', { class: 'v' }, s === 'nospend' ? '무지출' : v && v.exp ? shortWon(v.exp) : s === 'empty' ? '?' : ''));
    }));

  const sel = [...state.selected].sort();
  const actions = sel.length ? el('div', { class: 'card action-bar' },
    el('strong', {}, `${sel.length}일 선택`),
    el('div', { class: 'row gap wrap' },
      el('button', { type: 'button', class: 'btn primary', onclick: () => openBatch(sel) }, '지출 입력하기'),
      el('button', { type: 'button', class: 'btn soft', onclick: () => markNoSpend(sel) }, '지출 없음 표시'),
      el('button', { type: 'button', class: 'btn ghost', onclick: () => { state.selected.clear(); render(); } }, '선택 해제'))) : null;

  const single = sel.length === 1 ? d.transactions.filter((x) => x.date === sel[0]) : [];
  const singleCard = sel.length === 1 ? el('section', { class: 'card' },
    el('h3', {}, dayLabel(sel[0])),
    single.length ? el('ul', { class: 'tx-list' }, single.map((x) => txRow(x))) : el('p', { class: 'empty-msg' }, d.dayChecks[sel[0]] === 'nospend' ? '지출 없음으로 표시한 날이에요.' : '이 날은 기록이 없어요.'),
    d.dayChecks[sel[0]] ? el('button', { type: 'button', class: 'link', onclick: () => { delete d.dayChecks[sel[0]]; persist(); render(); } }, '확인 표시 지우기') : null) : null;

  return el('div', { class: 'stack' },
    el('section', { class: 'card recover-info' },
      el('p', {}, emptyDays.length || lowDays.length
        ? `기록이 없는 날 ${emptyDays.length}일${lowDays.length ? ` · 평소보다 기록이 적은 날 ${lowDays.length}일` : ''}`
        : '이 달은 빠진 날이 없어요 👏'),
      el('p', { class: 'fine' }, '기록이 없다고 돈을 쓴 건 아니에요. 지출이 없던 날은 "지출 없음"으로 표시하면 다시 묻지 않아요.'),
      emptyDays.length ? el('button', { type: 'button', class: 'btn soft small', onclick: () => { emptyDays.forEach((x) => state.selected.add(x)); render(); } }, '빈 날 모두 선택') : null),
    grid,
    el('div', { class: 'cal-legend' }, el('span', { class: 'lg recorded' }, '기록'), el('span', { class: 'lg nospend' }, '무지출'), el('span', { class: 'lg empty' }, '비어 있음'), el('span', { class: 'lg low' }, '적게 기록')),
    actions, singleCard);
}

function markNoSpend(dates) {
  const d = store.data;
  const prev = dates.map((x) => [x, d.dayChecks[x]]);
  let marked = 0; let reviewed = 0;
  for (const x of dates) {
    const hasExpense = d.transactions.some((tx) => tx.date === x && tx.type === 'expense');
    if (hasExpense) { d.dayChecks[x] = 'ok'; reviewed += 1; } else { d.dayChecks[x] = 'nospend'; marked += 1; }
  }
  state.selected.clear(); persist(); render();
  toast(`${marked}일 지출 없음${reviewed ? `, ${reviewed}일 확인 완료` : ''}으로 표시했어요`, () => {
    for (const [x, v] of prev) { if (v) d.dayChecks[x] = v; else delete d.dayChecks[x]; }
    persist(); render();
  });
}

/* 여러 날짜 일괄 입력 */
function openBatch(dates) {
  const quick = computeQuickItems(store.data, today(), 6);
  const sections = dates.map((date) => ({ date, nospend: false, rows: [] }));
  const body = el('div', { class: 'batch' });
  const saveBtn = el('button', { type: 'button', class: 'btn primary grow' }, '모두 저장');

  function newRow(sec, preset = {}) {
    const row = { amount: amountInput(preset.amount, { 'aria-label': '금액', placeholder: '금액' }), merchant: el('input', { type: 'text', placeholder: '사용처', maxlength: 60, value: preset.merchant || '', 'aria-label': '사용처' }), category: null };
    row.category = categorySelect('expense', preset.category || 'food', { 'aria-label': '카테고리' });
    row.merchant.addEventListener('change', () => { if (row.merchant.value.trim()) row.category.value = suggestCategory(store.data, row.merchant.value, 'expense').id; });
    sec.rows.push(row);
    return row;
  }
  function draw() {
    fill(body, 
      el('p', { class: 'fine' }, '기억나는 지출만 적어 주세요. 지출이 없던 날은 "지출 없음"을 체크해요.'),
      sections.map((sec) => {
        if (!sec.rows.length && !sec.nospend) newRow(sec);
        const ns = el('input', { type: 'checkbox', checked: sec.nospend });
        ns.addEventListener('change', () => { sec.nospend = ns.checked; if (ns.checked) sec.rows = []; draw(); });
        return el('section', { class: 'batch-day' },
          el('div', { class: 'row between' }, el('strong', {}, dayLabel(sec.date)), el('label', { class: 'check' }, ns, '지출 없음')),
          sec.nospend ? null : [
            sec.rows.map((r, i) => el('div', { class: 'batch-row' }, r.amount, r.merchant, r.category,
              el('button', { type: 'button', class: 'icon-btn', 'aria-label': '이 줄 삭제', onclick: () => { sec.rows.splice(i, 1); draw(); } }, icon('close', 16)))),
            el('div', { class: 'chips scroll' },
              el('button', { type: 'button', class: 'chip', onclick: () => { newRow(sec); draw(); } }, '+ 한 줄 추가'),
              quick.map((q) => el('button', { type: 'button', class: 'chip quick-chip', onclick: () => {
                const empty = sec.rows.find((r) => !readAmount(r.amount) && !r.merchant.value);
                if (empty) sec.rows.splice(sec.rows.indexOf(empty), 1);
                newRow(sec, q); draw();
              } }, `${getCategory(store.data, q.category).icon} ${q.merchant}`))),
          ]);
      }));
  }
  saveBtn.addEventListener('click', () => {
    const items = []; const noSpend = [];
    for (const sec of sections) {
      if (sec.nospend) { noSpend.push(sec.date); continue; }
      for (const r of sec.rows) {
        const amount = readAmount(r.amount);
        if (amount) items.push({ date: sec.date, type: 'expense', amount, merchant: r.merchant.value.trim(), category: r.category.value });
      }
    }
    if (!items.length && !noSpend.length) { toast('입력한 내용이 없어요.'); return; }
    const added = items.length ? addTransactions(items, 'batch') : [];
    for (const x of noSpend) if (!store.data.transactions.some((tx) => tx.date === x && tx.type === 'expense')) store.data.dayChecks[x] = 'nospend';
    for (const sec of sections) if (!sec.nospend && store.data.transactions.some((tx) => tx.date === sec.date)) store.data.dayChecks[sec.date] = 'ok';
    persist(); state.selected.clear(); closeSheet();
    toast(`${added.length}건 추가${noSpend.length ? `, ${noSpend.length}일 지출 없음` : ''}`);
  });
  draw();
  openSheet(`${dates.length}일 한 번에 채우기`, body, saveBtn);
}

/* ======================================================================
 * 통계
 * ==================================================================== */
function renderStats(t) {
  const mk = state.statsMonth;
  const d = store.data;
  const dash = computeDashboard(d, mk, t);
  const cats = dash.byCategory.filter((c) => c.amount > 0);
  const cmpLabel = dash.isCurrent ? '지난달 같은 기간' : '지난달';

  const summary = el('section', { class: 'card' },
    el('div', { class: 'sum-grid' },
      el('div', {}, el('span', { class: 'muted' }, '지출'), el('strong', {}, formatWon(dash.expense)), el('em', { class: dash.changePct > 0 ? 'up' : 'down' }, dash.changePct == null ? '비교 데이터 없음' : `${cmpLabel} 대비 ${formatPct(dash.changePct)}`)),
      el('div', {}, el('span', { class: 'muted' }, '수입'), el('strong', { class: 'pos' }, formatWon(dash.income))),
      el('div', {}, el('span', { class: 'muted' }, '수입 - 지출'), el('strong', { class: dash.net < 0 ? 'neg' : '' }, formatWon(dash.net))),
      el('div', {}, el('span', { class: 'muted' }, '하루 평균 지출'), el('strong', {}, formatWon(dash.dailyAvg)))));

  const budgetCard = el('section', { class: 'card' },
    el('div', { class: 'row between' }, el('h3', {}, '예산 대비 지출'), el('button', { type: 'button', class: 'link', onclick: openSettings }, dash.budget ? '예산 수정' : '예산 정하기')),
    dash.budget ? [
      el('p', {}, el('strong', {}, formatWon(dash.expense)), ` / ${formatWon(dash.budget)} (${Math.round(dash.budgetUsedPct)}%)`, dash.budgetInherited ? el('span', { class: 'fine' }, ' · 지난 예산 이어서 적용') : null),
      progressBar(dash.budgetUsedPct, { label: '예산 사용률' }),
      dash.isCurrent ? el('p', { class: 'fine' }, `지금 속도라면 월말 예상 지출 ${formatWon(dash.projected)} (하루 평균 × ${dash.daysInMonth}일, 앱 계산)`) : null,
      cats.filter((c) => c.budget).map((c) => el('div', { class: 'cat-budget' },
        el('div', { class: 'row between' }, el('span', {}, `${c.icon} ${c.name}`), el('span', { class: 'fine' }, `${formatWon(c.amount)} / ${formatWon(c.budget)}`)),
        progressBar(c.budgetPct, { label: `${c.name} 예산 사용률` }))),
    ] : el('p', { class: 'fine' }, '예산을 정하면 사용률과 초과 위험을 보여드려요.'));

  const catCard = el('section', { class: 'card' },
    el('h3', {}, '카테고리별 지출'),
    cats.length ? [
      el('div', { class: 'donut-center' }, donutChart(cats.map((c) => ({ value: c.amount, color: c.color, label: c.name })), { size: 190, thickness: 28, title: formatWon(dash.expense), subtitle: monthLabel(mk) })),
      el('ul', { class: 'cat-table' }, cats.map((c) => el('li', {},
        el('i', { style: { background: c.color }, 'aria-hidden': 'true' }),
        el('span', { class: 'grow' }, `${c.icon} ${c.name}`),
        el('span', { class: 'fine' }, `${Math.round(c.pct)}%`),
        el('strong', {}, formatWon(c.amount)),
        el('em', { class: c.changePct > 0 ? 'up' : 'down' }, c.changePct == null ? (c.lastSamePeriod ? '' : '신규') : formatPct(c.changePct))))),
      el('p', { class: 'fine' }, `증감률은 ${cmpLabel}과 비교한 값이에요.`),
    ] : el('p', { class: 'empty-msg' }, '이 달의 지출 기록이 없어요.'));

  const daily = dash.daily.map((x) => ({ label: String(Number(x.date.slice(8))), value: x.amount, muted: x.future, highlight: x.date === t }));
  const dailyCard = el('section', { class: 'card' },
    el('h3', {}, '일별 지출 추이'),
    barChart(daily, { avg: dash.dailyAvg, labelEvery: 5, ariaLabel: `일별 지출, 하루 평균 ${formatWon(dash.dailyAvg)}` }));

  const weekCard = el('section', { class: 'card' },
    el('h3', {}, '주간 비교'),
    el('div', { class: 'compare' },
      el('div', {}, el('span', { class: 'muted' }, '이번 주'), el('strong', {}, formatWon(dash.thisWeek))),
      el('div', {}, el('span', { class: 'muted' }, '지난주 같은 요일까지'), el('strong', {}, formatWon(dash.lastWeek))),
      el('div', {}, el('span', { class: 'muted' }, '변화'), el('strong', { class: dash.weekChangePct > 0 ? 'up' : 'down' }, formatPct(dash.weekChangePct)))));

  const monthCard = el('section', { class: 'card' },
    el('h3', {}, '월별 지출 비교'),
    barChart(dash.months.map((m) => ({ label: `${Number(m.month.slice(5))}월`, value: m.expense, highlight: m.month === mk, showValue: true })), { height: 160, ariaLabel: '최근 6개월 지출' }));

  const topCard = el('section', { class: 'card' },
    el('h3', {}, '이 달의 기록'),
    el('ul', { class: 'facts' },
      el('li', {}, el('span', {}, '가장 많이 쓴 카테고리'), el('strong', {}, dash.topCategory ? `${dash.topCategory.icon} ${dash.topCategory.name} ${formatWon(dash.topCategory.amount)}` : '-')),
      el('li', {}, el('span', {}, '가장 큰 지출'), el('strong', {}, dash.topTx ? `${txTitle(dash.topTx)} ${formatWon(dash.topTx.amount)}` : '-')),
      el('li', {}, el('span', {}, '자주 간 곳'), el('strong', {}, dash.topMerchants.length ? dash.topMerchants.slice(0, 3).map((m) => `${m.name} ${m.count}회`).join(', ') : '-')),
      el('li', {}, el('span', {}, '기록한 날'), el('strong', {}, `${dash.activeDays}일 / ${dash.elapsed}일`))));

  return el('div', { class: 'stack' }, monthNav(mk, (m) => { state.statsMonth = m; render(); }), summary, budgetCard, catCard, dailyCard, weekCard, monthCard, topCard);
}

/* ======================================================================
 * AI 코치
 * ==================================================================== */
function localAnswer(q) {
  const t = today(); const d = store.data;
  const dash = computeDashboard(d, monthOf(t), t);
  const missing = detectMissing(d, t);
  const ins = buildInsights(d, dash, missing);
  if (!d.transactions.length) return '아직 기록이 없어서 분석할 수 없어요. 며칠만 기록해 주시면 패턴을 알려드릴게요.';
  if (/리포트|보고서|정리/.test(q)) return localReport();
  if (/예산|초과|남은|남았/.test(q)) {
    if (!dash.budget) return '아직 이번 달 예산이 없어요. 오른쪽 위 설정에서 예산을 정하면 초과 가능성을 알려드릴게요.';
    return ins.filter((s) => /예산|예상|하루/.test(s)).join('\n') || `이번 달 예산의 ${Math.round(dash.budgetUsedPct)}%를 사용했어요.`;
  }
  if (/빠진|누락|안 ?적|놓친|빈 ?날/.test(q)) {
    const e = missing.filter((m) => m.kind === 'empty'); const l = missing.filter((m) => m.kind === 'low');
    if (!e.length && !l.length) return '최근 30일 동안 빠진 날이 없어요. 꾸준히 기록하고 있어요!';
    return [e.length ? `기록이 없는 날이 ${e.length}일 있어요: ${e.slice(-5).map((m) => dayLabel(m.date)).join(', ')}${e.length > 5 ? ' 등' : ''}.` : '',
      l.length ? `평소보다 기록이 적은 날도 ${l.length}일 있어요. 빠진 지출이 있는지 한 번 확인해 보세요.` : '',
      '지출이 없던 날이라면 거래내역 > 달력에서 "지출 없음"으로 표시해 주세요.'].filter(Boolean).join('\n');
  }
  const cat = d.categories.find((c) => q.includes(c.name) || c.name.split('·').some((p) => p.length > 1 && q.includes(p)));
  if (cat) {
    const c = dash.byCategory.find((x) => x.id === cat.id);
    if (!c || !c.amount) return `이번 달 ${cat.name} 기록은 아직 없어요.`;
    return `이번 달 ${cat.name} 지출은 ${formatWon(c.amount)}(전체의 ${Math.round(c.pct)}%)예요. 하루 평균 약 ${formatWon(c.amount / dash.elapsed)}이고, 지난달 같은 기간에는 ${formatWon(c.lastSamePeriod)}을 썼어요.${c.budget ? ` 예산 대비 ${Math.round(c.budgetPct)}% 사용했어요.` : ''}`;
  }
  if (/줄[이일여]|절약|아끼|아낄|과소비|많이 ?쓴|낭비/.test(q)) {
    const top = dash.byCategory.filter((c) => c.amount > 0).slice(0, 3);
    const rising = dash.byCategory.filter((c) => c.changePct != null && c.changePct >= 20 && c.lastSamePeriod >= 10000);
    return [`이번 달 지출이 큰 순서는 ${top.map((c) => `${c.name} ${formatWon(c.amount)}`).join(', ')}예요.`,
      rising.length ? `지난달 같은 기간보다 늘어난 곳은 ${rising.map((c) => `${c.name}(${formatPct(c.changePct)})`).join(', ')}이에요. 여기부터 주간 한도를 정해 보면 좋아요.` : '지난달보다 크게 늘어난 카테고리는 없어요.',
      dash.topMerchants[0] ? `가장 자주 간 곳은 ${dash.topMerchants[0].name}(${dash.topMerchants[0].count}회, ${formatWon(dash.topMerchants[0].amount)})이에요.` : ''].filter(Boolean).join('\n');
  }
  return ins.join('\n');
}

function localReport() {
  const t = today(); const d = store.data;
  const dash = computeDashboard(d, monthOf(t), t);
  const missing = detectMissing(d, t);
  const top = dash.byCategory.filter((c) => c.amount > 0).slice(0, 3);
  const rising = dash.byCategory.filter((c) => c.changePct != null && c.changePct >= 20 && c.lastSamePeriod >= 10000);
  const falling = dash.byCategory.filter((c) => c.changePct != null && c.changePct <= -20 && c.lastSamePeriod >= 10000);
  return [
    `📒 ${monthLabel(dash.month)} 소비 리포트 (${dayLabel(t)} 기준)`,
    `■ 한눈에 보기\n지출 ${formatWon(dash.expense)}, 수입 ${formatWon(dash.income)}${dash.changePct != null ? `, 지난달 같은 기간 대비 ${formatPct(dash.changePct)}` : ''}.`,
    `■ 많이 쓴 곳\n${top.map((c, i) => `${i + 1}. ${c.name} ${formatWon(c.amount)} (${Math.round(c.pct)}%)`).join('\n') || '기록 없음'}`,
    `■ 잘한 점\n${falling.length ? `${falling.map((c) => `${c.name} ${formatPct(c.changePct)}`).join(', ')} 줄였어요.` : `이번 달 ${dash.activeDays}일 기록했어요.`}`,
    `■ 신경 쓸 점\n${[dash.budget && dash.isCurrent && dash.projected > dash.budget ? `월말 예상 지출 ${formatWon(dash.projected)}로 예산 ${formatWon(dash.budget)}을 넘을 수 있어요.` : '', rising.length ? `${rising.map((c) => `${c.name} ${formatPct(c.changePct)}`).join(', ')} 늘었어요.` : ''].filter(Boolean).join('\n') || '크게 걱정할 부분은 없어요.'}`,
    `■ 기록 점검\n${missing.length ? `확인이 필요한 날 ${missing.length}일 (기록 없음 ${missing.filter((m) => m.kind === 'empty').length}일)` : '빠진 날 없음'}`,
  ].join('\n\n');
}

function looksLikeTransaction(q) {
  return !/[?？]|어때|알려|분석|얼마나|할까|뭐야|있어\?/.test(q) && parseNatural(store.data, q, today()).some((i) => i.amount);
}

async function ask(q, mode = 'chat') {
  const text = q.trim();
  if (!text && mode === 'chat') return;
  state.chat.push({ role: 'user', text: mode === 'report' ? '이번 달 리포트 만들어 줘' : text });
  if (mode === 'chat' && looksLikeTransaction(text)) {
    state.chat.push({ role: 'bot', text: '지출 기록처럼 보여요. 기록으로 남길까요? 저장 전에 내용을 확인할 수 있어요.', action: { label: '기록 확인하기', run: () => openEntry({ mode: 'nl', text }) } });
    render(); return;
  }
  const pending = { role: 'bot', text: '생각하는 중…', pending: true };
  state.chat.push(pending); render();
  let answer; let by = 'local';
  if (state.ai.available) {
    try {
      answer = (await api('/api/chat', { mode, question: text, context: buildAiContext(store.data, today()) })).text; by = 'ai';
    } catch (e) { answer = `${e.message}\n대신 앱이 계산한 내용으로 답할게요.\n\n${mode === 'report' ? localReport() : localAnswer(text)}`; }
  }
  if (!answer) answer = mode === 'report' ? localReport() : localAnswer(text);
  Object.assign(pending, { text: answer, pending: false, by });
  if (mode === 'report') {
    store.data.aiReports.push({ month: monthOf(today()), text: answer, createdAt: new Date().toISOString(), by });
    store.data.aiReports = store.data.aiReports.slice(-24); persist();
  }
  render();
  const log = $('.chat-log'); if (log) log.lastElementChild?.scrollIntoView({ block: 'nearest' });
}

function renderAi(t) {
  const d = store.data;
  const dash = computeDashboard(d, monthOf(t), t);
  const insights = buildInsights(d, dash, detectMissing(d, t));
  const statusPill = el('p', { class: `pill ${state.ai.available ? 'on' : ''}` }, state.ai.available ? `AI 연결됨 · ${state.ai.model}` : '오프라인 모드 · 앱 계산으로 답해요');
  const insightCard = el('section', { class: 'card' },
    el('div', { class: 'row between' }, el('h3', {}, '모모의 분석'), statusPill),
    el('ul', { class: 'insights' }, insights.map((s) => el('li', {}, s))),
    el('p', { class: 'fine' }, '모든 금액은 저장된 기록으로 앱이 직접 계산했어요.'));

  const suggestions = ['이번 달 소비 분석해 줘', '어디서 줄일 수 있을까?', '예산 초과할까?', '빠진 기록 있어?', '카페 지출 어때?'];
  const log = el('div', { class: 'chat-log', 'aria-live': 'polite' },
    state.chat.length ? state.chat.map((m) => el('div', { class: `msg ${m.role}${m.pending ? ' pending' : ''}` },
      el('p', {}, m.text),
      m.action ? el('button', { type: 'button', class: 'btn soft small', onclick: m.action.run }, m.action.label) : null))
      : el('p', { class: 'empty-msg' }, '소비에 대해 무엇이든 물어보세요. "스타벅스 6500원"처럼 적으면 기록도 도와드려요.'));
  const input = el('input', { type: 'text', id: 'chat-input', maxlength: 600, placeholder: '모모에게 물어보기', autocomplete: 'off', 'aria-label': '질문' });
  const form = el('form', { class: 'chat-form', onsubmit: (e) => { e.preventDefault(); const q = input.value; input.value = ''; ask(q); } },
    input, el('button', { type: 'submit', class: 'icon-btn send', 'aria-label': '보내기' }, icon('send', 20)));

  const reports = d.aiReports.slice().reverse();
  const reportCard = el('section', { class: 'card' },
    el('div', { class: 'row between' }, el('h3', {}, '월간 리포트'),
      el('button', { type: 'button', class: 'btn soft small', onclick: () => ask('', 'report') }, '이번 달 리포트 만들기')),
    reports.length ? reports.slice(0, 6).map((r) => el('details', { class: 'report' },
      el('summary', {}, `${monthLabel(r.month)} · ${dayLabel(r.createdAt.slice(0, 10))} 작성${r.by === 'ai' ? ' (AI)' : ''}`),
      el('p', { class: 'pre' }, r.text))) : el('p', { class: 'fine' }, '만든 리포트는 이 기기에 보관돼요.'));

  return el('div', { class: 'stack' }, insightCard,
    el('section', { class: 'card chat' },
      el('div', { class: 'chips scroll' }, suggestions.map((s) => el('button', { type: 'button', class: 'chip', onclick: () => ask(s) }, s))),
      log, form),
    reportCard);
}

/* ======================================================================
 * 모모 (캐릭터 · 목표 · 미션)
 * ==================================================================== */
function renderMomo(t) {
  const d = store.data;
  const ch = computeCharacter(d, t);
  const missions = computeMissions(d, t);

  const hero = el('section', { class: 'card momo-hero' },
    mascotSvg({ stage: ch.stage, item: ch.equipped, size: 150 }),
    el('h2', {}, ch.stageName),
    el('p', { class: 'fine' }, ch.stageDesc),
    el('div', { class: 'row between lv' }, el('strong', {}, `Lv.${ch.level}`), el('span', { class: 'fine' }, `${ch.levelXp} / ${ch.levelNeed} XP`)),
    progressBar((ch.levelXp / ch.levelNeed) * 100, { warn: 101, label: '레벨 경험치' }),
    el('div', { class: 'momo-stats' },
      el('div', {}, el('strong', {}, `🔥 ${ch.streak}일`), el('span', { class: 'fine' }, '연속 기록')),
      el('div', {}, el('strong', {}, `${ch.activeDays}일`), el('span', { class: 'fine' }, '기록한 날')),
      el('div', {}, el('strong', {}, `${ch.keptMonths.length}달`), el('span', { class: 'fine' }, '예산 지킴'))),
    ch.nextStage ? el('p', { class: 'fine' }, `다음 성장: ${ch.nextStage.name} — 예산 지킨 달 ${ch.keptMonths.length}/${ch.nextStage.min}`) : el('p', { class: 'fine' }, '최고 단계에 도달했어요!'));

  const items = el('section', { class: 'card' },
    el('h3', {}, '아이템'),
    el('div', { class: 'items' }, ITEMS.map((it, i) => {
      const owned = ch.unlocked.includes(it.id);
      return el('button', {
        type: 'button', class: `item ${owned ? '' : 'locked'}`, disabled: !owned, 'aria-pressed': String(ch.equipped === it.id),
        onclick: () => { d.character.equipped = ch.equipped === it.id ? null : it.id; persist(); render(); },
      }, el('span', { class: 'item-ico', 'aria-hidden': 'true' }, owned ? it.icon : '🔒'), el('span', {}, owned ? it.name : `목표 ${i + 1}개 달성`));
    })),
    el('p', { class: 'fine' }, '저축 목표를 달성할 때마다 새 아이템을 받아요.'));

  const goals = el('section', { class: 'card' },
    el('div', { class: 'row between' }, el('h3', {}, '저축 목표'), el('button', { type: 'button', class: 'btn soft small', onclick: openGoalForm }, '+ 목표 추가')),
    d.goals.length ? d.goals.map((g) => {
      const saved = goalSaved(g);
      const pct = (saved / g.target) * 100;
      return el('div', { class: 'goal' },
        el('div', { class: 'row between' }, el('strong', {}, `${g.achievedAt ? '🏆 ' : ''}${g.name}`), el('span', { class: 'fine' }, `${Math.round(Math.min(pct, 999))}%`)),
        progressBar(pct, { warn: 101, label: `${g.name} 달성률` }),
        el('div', { class: 'row between' }, el('span', { class: 'fine' }, `${formatWon(saved)} / ${formatWon(g.target)}`),
          el('div', { class: 'row gap' },
            el('button', { type: 'button', class: 'btn soft small', onclick: () => openDeposit(g) }, '저금하기'),
            el('button', { type: 'button', class: 'btn ghost small', 'aria-label': `${g.name} 삭제`, onclick: () => {
              if (!confirm(`'${g.name}' 목표를 삭제할까요?`)) return;
              d.goals = d.goals.filter((x) => x.id !== g.id); persist(); render();
            } }, '삭제'))));
    }) : el('p', { class: 'empty-msg' }, '여행, 비상금처럼 모으고 싶은 목표를 만들어 보세요.'));

  const missionCard = el('section', { class: 'card' },
    el('h3', {}, `${Number(t.slice(5, 7))}월 미션`),
    el('ul', { class: 'missions' }, missions.map((m) => el('li', { class: m.done ? 'done' : m.failed ? 'failed' : '' },
      el('div', { class: 'row between' }, el('span', {}, `${m.icon} ${m.title}`), el('span', { class: 'fine' }, m.done ? '완료 ✓' : m.failed ? '아쉬워요' : `${Math.min(m.progress, m.target)}/${m.target}`)),
      m.id !== 'cafe' ? progressBar((m.progress / m.target) * 100, { warn: 101, label: m.title }) : null,
      m.note ? el('p', { class: 'fine' }, m.note) : null))),
    el('p', { class: 'fine' }, '지난달에 완료한 미션은 경험치로 쌓여요.'));

  const record = el('section', { class: 'card' },
    el('h3', {}, '달성 기록'),
    ch.keptMonths.length || ch.achievedGoals.length ? el('ul', { class: 'facts' },
      ch.keptMonths.map((mk) => el('li', {}, el('span', {}, '🎯 예산 지킴'), el('strong', {}, monthLabel(mk)))),
      ch.achievedGoals.map((g) => el('li', {}, el('span', {}, `🏆 ${g.name}`), el('strong', {}, dayLabel(g.achievedAt.slice(0, 10))))))
      : el('p', { class: 'fine' }, '첫 달성을 기다리고 있어요.'),
    el('details', { class: 'rules' }, el('summary', {}, '모모는 어떻게 성장하나요?'),
      el('ul', {},
        el('li', {}, `기록한 날마다 +${XP_RULES.activeDay} XP (하루 한 번만 — 많이 쓴다고 더 주지 않아요)`),
        el('li', {}, `'지출 없음'으로 확인한 날도 기록한 날이에요`),
        el('li', {}, `지난달 미션 완료마다 +${XP_RULES.missionDone} XP`),
        el('li', {}, `예산을 지킨 달 +${XP_RULES.keptMonth} XP, 성장 단계 상승 (그 달 70% 이상 기록했을 때만)`),
        el('li', {}, `저축 목표 달성 +${XP_RULES.goalAchieved} XP와 새 아이템`))));

  return el('div', { class: 'stack' }, hero, missionCard, goals, items, record);
}

function openGoalForm() {
  const name = el('input', { type: 'text', id: 'g-name', maxlength: 30, placeholder: '예) 제주도 여행', required: true });
  const target = amountInput('', { id: 'g-target', 'aria-label': '목표 금액' });
  const err = el('p', { class: 'error', role: 'alert' });
  const save = el('button', { type: 'button', class: 'btn primary grow', onclick: () => {
    const amount = readAmount(target);
    if (!name.value.trim()) { err.textContent = '목표 이름을 적어 주세요.'; name.focus(); return; }
    if (!amount) { err.textContent = '목표 금액을 적어 주세요.'; target.focus(); return; }
    store.data.goals.push({ id: uid(), name: name.value.trim(), target: amount, deposits: [], createdAt: new Date().toISOString(), achievedAt: null });
    persist(); closeSheet(); toast('새 목표를 만들었어요');
  } }, '목표 만들기');
  openSheet('저축 목표 만들기', el('div', { class: 'stack tight' },
    el('label', { class: 'label', for: 'g-name' }, '목표 이름'), name,
    el('label', { class: 'label', for: 'g-target' }, '목표 금액'), el('div', { class: 'amount-field small' }, target, el('span', {}, '원')), err), save);
  setTimeout(() => name.focus(), 60);
}

function openDeposit(goal) {
  const amt = amountInput('', { id: 'd-amount', 'aria-label': '저금할 금액' });
  const save = el('button', { type: 'button', class: 'btn primary grow', onclick: () => {
    const v = readAmount(amt);
    if (!v) { amt.focus(); return; }
    const dep = { id: uid(), date: today(), amount: v };
    goal.deposits.push(dep);
    const wasAchieved = Boolean(goal.achievedAt);
    if (!goal.achievedAt && goalSaved(goal) >= goal.target) goal.achievedAt = new Date().toISOString();
    persist(); closeSheet();
    toast(!wasAchieved && goal.achievedAt ? '🎉 목표 달성! 모모가 새 아이템을 받았어요' : `${formatWon(v)} 저금했어요`, () => {
      goal.deposits = goal.deposits.filter((x) => x.id !== dep.id);
      if (!wasAchieved) goal.achievedAt = null;
      persist(); render();
    });
  } }, '저금하기');
  openSheet(`${goal.name}에 저금`, el('div', { class: 'stack tight' },
    el('p', { class: 'fine' }, `지금까지 ${formatWon(goalSaved(goal))} / ${formatWon(goal.target)}`),
    el('div', { class: 'amount-field' }, amt, el('span', {}, '원')),
    el('p', { class: 'fine' }, '저금 기록은 지출 통계에 포함되지 않아요. 실제로 저축 계좌에 옮긴 금액을 적어 주세요.')), save);
  setTimeout(() => amt.focus(), 60);
}

/* ======================================================================
 * 설정: 예산 · 카테고리 · 백업
 * ==================================================================== */
function openSettings() {
  const d = store.data;
  const mk = monthOf(today());
  const budget = getBudget(d, mk);
  const total = amountInput(budget.total || '', { id: 's-total', 'aria-label': '이번 달 총예산' });
  const catInputs = d.categories.filter((c) => c.type === 'expense').map((c) => ({ c, input: amountInput((budget.byCategory || {})[c.id] || '', { 'aria-label': `${c.name} 예산` }) }));
  const saveBudget = el('button', { type: 'button', class: 'btn primary', onclick: () => {
    const byCategory = {};
    for (const { c, input } of catInputs) { const v = readAmount(input); if (v) byCategory[c.id] = v; }
    d.budgets[mk] = { total: readAmount(total), byCategory };
    persist(); toast(`${monthLabel(mk)} 예산을 저장했어요`); render();
  } }, '예산 저장');

  const catList = el('div', { class: 'cat-manage' });
  function drawCats() {
    fill(catList, ...['expense', 'income'].map((type) => el('div', {},
      el('p', { class: 'label' }, type === 'expense' ? '지출 카테고리' : '수입 카테고리'),
      d.categories.filter((c) => c.type === type).map((c) => {
        const name = el('input', { type: 'text', value: c.name, maxlength: 20, 'aria-label': `${c.name} 이름` });
        name.addEventListener('change', () => { if (name.value.trim()) { c.name = name.value.trim(); persist(); } else name.value = c.name; });
        const locked = c.id === 'etc' || c.id === 'income_etc';
        return el('div', { class: 'cat-line' }, el('span', { class: 'tx-ico', style: { background: c.color } }, c.icon), name,
          locked ? el('span', { class: 'fine' }, '기본') : el('button', { type: 'button', class: 'icon-btn', 'aria-label': `${c.name} 삭제`, onclick: () => {
            const n = d.transactions.filter((t) => t.category === c.id).length;
            if (!confirm(n ? `'${c.name}' 기록 ${n}건은 '기타'로 옮겨져요. 삭제할까요?` : `'${c.name}'을 삭제할까요?`)) return;
            const fallback = c.type === 'income' ? 'income_etc' : 'etc';
            d.transactions.forEach((t) => { if (t.category === c.id) t.category = fallback; });
            Object.values(d.budgets).forEach((b) => { delete b.byCategory[c.id]; });
            d.categories = d.categories.filter((x) => x.id !== c.id);
            persist(); drawCats();
          } }, icon('close', 16)));
      }))));
  }
  drawCats();
  const newName = el('input', { type: 'text', maxlength: 20, placeholder: '새 카테고리 이름', 'aria-label': '새 카테고리 이름' });
  const newIcon = el('input', { type: 'text', maxlength: 4, value: '🏷️', class: 'emoji-input', 'aria-label': '아이콘(이모지)' });
  const newType = el('select', { 'aria-label': '유형' }, el('option', { value: 'expense' }, '지출'), el('option', { value: 'income' }, '수입'));
  const palette = ['#F4A7B9', '#C9A7EB', '#8FCFC0', '#F7C08A', '#9DBFE3', '#B3B6E6', '#F5D08A', '#BFDDA0'];
  const addCat = el('button', { type: 'button', class: 'btn soft', onclick: () => {
    const nm = newName.value.trim();
    if (!nm) { newName.focus(); return; }
    d.categories.push({ id: `c_${uid()}`, name: nm, icon: newIcon.value.trim() || '🏷️', type: newType.value, color: palette[d.categories.length % palette.length] });
    persist(); newName.value = ''; drawCats(); toast(`'${nm}' 카테고리를 추가했어요`);
  } }, '추가');

  const fileIn = el('input', { type: 'file', accept: 'application/json,.json', id: 'restore-file', class: 'visually-hidden' });
  fileIn.addEventListener('change', async () => {
    const f = fileIn.files && fileIn.files[0];
    if (!f) return;
    try {
      const parsed = normalizeData(JSON.parse(await f.text()));
      if (!confirm(`백업 파일의 기록 ${parsed.transactions.length}건으로 현재 데이터(${d.transactions.length}건)를 바꿀까요?`)) return;
      store.replace(parsed); closeSheet(); toast('백업을 불러왔어요');
    } catch { toast('백업 파일을 읽지 못했어요.'); } finally { fileIn.value = ''; }
  });
  let autoBackup = null;
  try { autoBackup = JSON.parse(localStorage.getItem('momo-budget-v1-autobackup') || 'null'); } catch { /* ignore */ }

  openSheet('설정', el('div', { class: 'settings stack' },
    el('section', {},
      el('h3', {}, `${monthLabel(mk)} 예산`),
      budget.inherited ? el('p', { class: 'fine' }, '지난 예산을 이어서 쓰고 있어요. 저장하면 이번 달 예산이 돼요.') : null,
      el('label', { class: 'label', for: 's-total' }, '한 달 총예산'),
      el('div', { class: 'amount-field small' }, total, el('span', {}, '원')),
      el('details', {}, el('summary', {}, '카테고리별 예산 (선택)'),
        el('div', { class: 'budget-cats' }, catInputs.map(({ c, input }) => el('label', { class: 'budget-line' }, el('span', {}, `${c.icon} ${c.name}`), input)))),
      saveBudget),
    el('section', {},
      el('h3', {}, '카테고리 관리'), catList,
      el('div', { class: 'row gap add-cat' }, newIcon, newName, newType, addCat)),
    el('section', {},
      el('h3', {}, '백업'),
      el('p', { class: 'fine' }, `기록은 이 기기 브라우저에 저장돼요. 하루 한 번 자동 사본도 보관해요.${d.meta.lastBackupAt ? ` 마지막 백업: ${dayLabel(d.meta.lastBackupAt.slice(0, 10))}` : ' 아직 백업 파일을 받은 적이 없어요.'}`),
      el('div', { class: 'row gap wrap' },
        el('button', { type: 'button', class: 'btn soft', onclick: downloadBackup }, '백업 파일 받기'),
        el('label', { class: 'btn soft', for: 'restore-file' }, '백업 불러오기'), fileIn,
        autoBackup ? el('button', { type: 'button', class: 'btn ghost', onclick: () => {
          if (!confirm(`${autoBackup.date} 자동 사본(기록 ${(autoBackup.data.transactions || []).length}건)으로 되돌릴까요?`)) return;
          store.replace(autoBackup.data); closeSheet(); toast('자동 사본으로 되돌렸어요');
        } }, `자동 사본으로 되돌리기 (${autoBackup.date})`) : null)),
    el('section', {},
      el('h3', {}, '개인정보'),
      el('p', { class: 'fine' }, '거래 기록은 서버로 보내지 않아요. AI 기능을 쓸 때만 질문·집계값·캡처 이미지가 Gemini로 전송되고, 서버에는 저장되지 않아요.'),
      el('button', { type: 'button', class: 'btn danger-ghost', onclick: () => {
        if (!confirm('모든 기록을 지울까요? 되돌릴 수 없어요. (먼저 백업을 권해요)')) return;
        if (!confirm('정말 지울까요?')) return;
        store.replace(createEmptyData()); closeSheet(); toast('모든 데이터를 지웠어요');
      } }, '모든 데이터 지우기'))));
}

function downloadBackup() {
  store.data.meta.lastBackupAt = new Date().toISOString();
  persist();
  const blob = new Blob([JSON.stringify(store.data, null, 2)], { type: 'application/json' });
  const a = el('a', { href: URL.createObjectURL(blob), download: `momo-budget-backup-${today()}.json` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  toast('백업 파일을 내려받았어요'); render();
}

/* ---------- 라우팅 ---------- */
const TITLES = { home: '모모 가계부', history: '거래내역', stats: '통계', ai: 'AI 코치', momo: '모모와 목표' };
const RENDERERS = { home: renderHome, history: renderHistory, stats: renderStats, ai: renderAi, momo: renderMomo };

function setTab(tab) { state.tab = tab; render(); window.scrollTo(0, 0); $('#view').focus({ preventScroll: true }); }

function render() {
  for (const b of document.querySelectorAll('.tabbar button')) {
    const on = b.dataset.tab === state.tab;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  }
  $('#screen-title').textContent = TITLES[state.tab];
  const focusedId = document.activeElement && document.activeElement.id;
  fill($('#view'), RENDERERS[state.tab](today()));
  if (focusedId === 'chat-input') $('#chat-input')?.focus();
}

document.querySelectorAll('.tabbar button').forEach((b) => b.addEventListener('click', () => setTab(b.dataset.tab)));
$('#fab').addEventListener('click', () => openEntry());
$('#settings-btn').addEventListener('click', openSettings);
window.addEventListener('storage', (e) => { if (e.key === STORAGE_KEY) { store.load(); render(); } });

if (store.lastError) toast('저장된 데이터를 읽지 못해 자동 사본으로 복구했어요.');
render();
checkAi();
