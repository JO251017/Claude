const STORAGE_KEY = 'reminders';

let reminders = loadReminders();

// Set default datetime to now + 1 hour
const datetimeInput = document.getElementById('datetime');
const now = new Date();
now.setHours(now.getHours() + 1);
now.setSeconds(0);
now.setMilliseconds(0);
datetimeInput.value = now.toISOString().slice(0, 16);

document.getElementById('reminder-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const title = document.getElementById('title').value.trim();
  const datetime = document.getElementById('datetime').value;
  const note = document.getElementById('note').value.trim();

  if (!title || !datetime) return;

  const reminder = {
    id: Date.now().toString(),
    title,
    datetime,
    note,
    done: false,
  };

  reminders.push(reminder);
  saveReminders();
  renderReminders();
  e.target.reset();

  // Reset datetime to now + 1 hour
  const next = new Date();
  next.setHours(next.getHours() + 1);
  next.setSeconds(0);
  next.setMilliseconds(0);
  datetimeInput.value = next.toISOString().slice(0, 16);
});

function deleteReminder(id) {
  reminders = reminders.filter((r) => r.id !== id);
  saveReminders();
  renderReminders();
}

function toggleDone(id) {
  const r = reminders.find((r) => r.id === id);
  if (r) {
    r.done = !r.done;
    saveReminders();
    renderReminders();
  }
}

function renderReminders() {
  const container = document.getElementById('reminders-container');
  const emptyMsg = document.getElementById('empty-msg');

  const sorted = [...reminders].sort((a, b) => {
    if (a.done !== b.done) return a.done ? 1 : -1;
    return new Date(a.datetime) - new Date(b.datetime);
  });

  container.querySelectorAll('.reminder-card').forEach((el) => el.remove());

  // Capture now once — used for both stats and per-card status
  const nowMs = Date.now();

  let upcoming = 0, overdue = 0, done = 0;
  reminders.forEach(r => {
    if (r.done) done++;
    else if (new Date(r.datetime).getTime() < nowMs) overdue++;
    else upcoming++;
  });
  document.getElementById('stat-upcoming').textContent = upcoming;
  document.getElementById('stat-overdue').textContent  = overdue;
  document.getElementById('stat-done').textContent     = done;

  if (sorted.length === 0) {
    emptyMsg.classList.remove('hidden');
    return;
  }
  emptyMsg.classList.add('hidden');

  const badgeLabels = { done: '✓ 완료', overdue: '⚠ 기한 초과', upcoming: '● 예정' };

  sorted.forEach((r) => {
    const card = document.createElement('div');
    const isOverdue = !r.done && new Date(r.datetime).getTime() < nowMs;
    const status = r.done ? 'done' : isOverdue ? 'overdue' : 'upcoming';

    card.className = `reminder-card ${status}`;

    card.innerHTML = `
      <div class="reminder-info">
        <span class="badge ${status}">${badgeLabels[status]}</span>
        <div class="title">${escapeHtml(r.title)}</div>
        <div class="time">🕐 ${formatDatetime(r.datetime)}</div>
        ${r.note ? `<div class="note">${escapeHtml(r.note)}</div>` : ''}
      </div>
      <div class="reminder-actions">
        <button class="btn-done" data-id="${escapeHtml(r.id)}">${r.done ? '취소' : '완료'}</button>
        <button class="btn-delete" data-id="${escapeHtml(r.id)}">삭제</button>
      </div>
    `;

    card.querySelector('.btn-done').addEventListener('click', () => toggleDone(r.id));
    card.querySelector('.btn-delete').addEventListener('click', () => deleteReminder(r.id));

    container.appendChild(card);
  });
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

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function saveReminders() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(reminders));
}

function loadReminders() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

// Check for due reminders every 30 seconds
function checkReminders() {
  const now = new Date();
  reminders.forEach((r) => {
    if (!r.done && !r.notified) {
      const due = new Date(r.datetime);
      if (due <= now) {
        showNotification(r.title);
        r.notified = true;
        saveReminders();
        renderReminders();
      }
    }
  });
}

function showNotification(title) {
  const banner = document.getElementById('notification-banner');
  document.getElementById('notification-text').textContent = `알림: ${title}`;
  banner.classList.remove('hidden');

  // Browser notification if permitted
  if (Notification.permission === 'granted') {
    new Notification('미리 알림', { body: title });
  }
}

function dismissNotification() {
  document.getElementById('notification-banner').classList.add('hidden');
}

// Request notification permission
if ('Notification' in window && Notification.permission === 'default') {
  Notification.requestPermission();
}

// Initial render and start polling
renderReminders();
setInterval(checkReminders, 30000);
checkReminders();
