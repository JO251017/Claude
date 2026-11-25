const STORAGE_KEY = 'reminders';
const CHECK_INTERVAL_MS = 30000;

let storageAvailable = true;
let reminders = loadReminders();

const form = document.getElementById('reminder-form');
const datetimeInput = document.getElementById('datetime');
const container = document.getElementById('reminders-container');
const emptyMsg = document.getElementById('empty-msg');
const banner = document.getElementById('notification-banner');
const bannerText = document.getElementById('notification-text');
const notifyStatus = document.getElementById('notify-status');
const notifyButton = document.getElementById('notify-enable');

// ---- Date helpers ----

// datetime-local needs local time ("YYYY-MM-DDTHH:mm"); toISOString() would give UTC.
function toLocalInputValue(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function setDefaultDatetime() {
  const next = new Date();
  next.setHours(next.getHours() + 1);
  next.setSeconds(0, 0);
  datetimeInput.value = toLocalInputValue(next);
}

function formatDatetime(datetimeStr) {
  const d = new Date(datetimeStr);
  return d.toLocaleString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ---- Storage (may be unavailable in private windows or embedded views) ----

function saveReminders() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(reminders));
  } catch {
    storageAvailable = false;
  }
  document.getElementById('storage-warning').hidden = storageAvailable;
}

function loadReminders() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    storageAvailable = false;
    return [];
  }
}

// ---- Actions ----

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const title = document.getElementById('title').value.trim();
  const datetime = datetimeInput.value;
  const note = document.getElementById('note').value.trim();

  if (!title || !datetime) return;

  reminders.push({
    id: Date.now().toString(),
    title,
    datetime,
    note,
    done: false,
  });

  saveReminders();
  renderReminders();
  form.reset();
  setDefaultDatetime();
  document.getElementById('title').focus();
});

function deleteReminder(id) {
  reminders = reminders.filter((r) => r.id !== id);
  saveReminders();
  renderReminders();
}

function toggleDone(id) {
  const r = reminders.find((item) => item.id === id);
  if (r) {
    r.done = !r.done;
    saveReminders();
    renderReminders();
  }
}

// Event delegation: no inline onclick handlers (blocked by strict CSP in installed apps).
container.addEventListener('click', (e) => {
  const button = e.target.closest('button[data-action]');
  if (!button) return;
  const { action, id } = button.dataset;
  if (action === 'toggle') toggleDone(id);
  if (action === 'delete') deleteReminder(id);
});

// ---- Rendering (DOM text APIs only; titles and notes are user input) ----

const BADGE_LABELS = { done: '완료', overdue: '기한 초과', upcoming: '예정' };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderReminders() {
  const sorted = [...reminders].sort((a, b) => {
    if (a.done !== b.done) return a.done ? 1 : -1;
    return new Date(a.datetime) - new Date(b.datetime);
  });

  container.querySelectorAll('.reminder-card').forEach((node) => node.remove());
  emptyMsg.hidden = sorted.length > 0;

  const now = new Date();
  sorted.forEach((r) => {
    const isOverdue = !r.done && new Date(r.datetime) < now;
    const status = r.done ? 'done' : isOverdue ? 'overdue' : 'upcoming';

    const card = el('article', `reminder-card ${status}`);
    const info = el('div', 'reminder-info');
    info.append(
      el('span', `badge ${status}`, BADGE_LABELS[status]),
      el('div', 'title', r.title),
      el('div', 'time', formatDatetime(r.datetime))
    );
    if (r.note) info.append(el('div', 'note', r.note));

    const actions = el('div', 'reminder-actions');
    const doneBtn = el('button', 'btn-done', r.done ? '취소' : '완료');
    doneBtn.type = 'button';
    doneBtn.dataset.action = 'toggle';
    doneBtn.dataset.id = r.id;
    doneBtn.setAttribute('aria-label', `${r.title} ${r.done ? '완료 취소' : '완료 처리'}`);

    const deleteBtn = el('button', 'btn-delete', '삭제');
    deleteBtn.type = 'button';
    deleteBtn.dataset.action = 'delete';
    deleteBtn.dataset.id = r.id;
    deleteBtn.setAttribute('aria-label', `${r.title} 삭제`);

    actions.append(doneBtn, deleteBtn);
    card.append(info, actions);
    container.appendChild(card);
  });
}

// ---- Notifications ----

const hasNotificationApi = 'Notification' in window;

function updateNotifyControl() {
  if (!hasNotificationApi) {
    notifyStatus.textContent = '이 환경은 시스템 알림을 지원하지 않아 화면 배너로 알려 드립니다.';
    notifyButton.hidden = true;
    return;
  }
  const states = {
    granted: '시스템 알림: 켜짐',
    denied: '시스템 알림이 차단되어 화면 배너로만 알려 드립니다.',
    default: '시스템 알림: 꺼짐',
  };
  notifyStatus.textContent = states[Notification.permission] || states.default;
  notifyButton.hidden = Notification.permission !== 'default';
}

// Permission is requested only from this user click.
notifyButton.addEventListener('click', async () => {
  try {
    await Notification.requestPermission();
  } catch {
    // Some embedded views reject the request; fall back to the in-page banner.
  }
  updateNotifyControl();
});

function showNotification(title) {
  bannerText.textContent = `알림: ${title}`;
  banner.hidden = false;

  if (hasNotificationApi && Notification.permission === 'granted') {
    try {
      new Notification('미리 알림', { body: title });
    } catch {
      // Constructor can throw in some contexts; the banner is already shown.
    }
  }
}

document.getElementById('notification-dismiss').addEventListener('click', () => {
  banner.hidden = true;
});

function checkReminders() {
  const now = new Date();
  let changed = false;
  reminders.forEach((r) => {
    if (!r.done && !r.notified && new Date(r.datetime) <= now) {
      showNotification(r.title);
      r.notified = true;
      changed = true;
    }
  });
  if (changed) saveReminders();
  // Re-render each tick so "예정" turns into "기한 초과" without a reload.
  renderReminders();
}

// ---- Start ----

setDefaultDatetime();
updateNotifyControl();
document.getElementById('storage-warning').hidden = storageAvailable;
renderReminders();
checkReminders();
setInterval(checkReminders, CHECK_INTERVAL_MS);
