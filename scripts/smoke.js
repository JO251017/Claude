// Browser smoke test for the reminder app. Dev-only: needs Playwright installed
// (preinstalled in Claude Code cloud sessions). Usage: node scripts/smoke.js [screenshot-dir]
const path = require('path');
const { chromium } = require('playwright');

const url = 'file://' + path.resolve(__dirname, '..', 'index.html');
const shotDir = process.argv[2];
const results = [];
const check = (name, ok, detail = '') => results.push({ name, ok: !!ok, detail });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ timezoneId: 'Asia/Seoul', viewport: { width: 720, height: 1000 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.clock.setSystemTime(new Date('2026-11-25T22:00:00+09:00'));

  await page.goto(url);
  await page.evaluate(() => localStorage.setItem('reminders', JSON.stringify([
    { id: 'legacy', title: '옛 알림', datetime: '2026-12-01T09:00', note: '', done: false },
  ])));
  await page.reload();

  const v = await page.inputValue('#datetime');
  check('default datetime is local now + 1h', v.slice(11, 13) === '23', v);

  const add = async (title, dt, repeat = '') => {
    await page.fill('#title', title);
    await page.fill('#datetime', dt);
    if (await page.$('#repeat')) await page.selectOption('#repeat', repeat);
    await page.click('button[type=submit]');
  };
  const card = (t) => page.locator('.reminder-card', { hasText: t });

  await add('<b>지난 일</b>', '2020-01-01T09:00');
  check('title is escaped', (await card('<b>지난 일</b>').count()) === 1);
  await add('나중 일', '2030-01-01T09:00');
  await add('지울 일', '2030-06-01T09:00');
  await card('지울 일').locator('.btn-delete').click();
  check('delete removes card', (await card('지울 일').count()) === 0);

  if (await page.$('#repeat')) {
    await add('매일 약', '2026-11-20T08:00', 'daily');
    await add('월세', '2027-01-31T09:00', 'monthly');
    await card('매일 약').locator('.btn-done').click();
    await card('월세').locator('.btn-done').click();
  }
  await card('옛 알림').locator('.btn-done').click();

  await page.reload();
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('reminders')));
  const by = (t) => stored.find((r) => r.title === t) || {};
  check('legacy reminder toggles done', by('옛 알림').done === true);
  if (by('매일 약').repeat) {
    check('daily skips missed days', by('매일 약').datetime === '2026-11-26T08:00', by('매일 약').datetime);
    check('monthly clamps to month end', by('월세').datetime === '2027-02-28T09:00', by('월세').datetime);
  }
  const titles = await page.$$eval('.reminder-card .title', (els) => els.map((e) => e.textContent));
  check('done items sort last', titles[titles.length - 1] === '옛 알림', titles.join(', '));

  await page.keyboard.press('Tab');
  check('visible focus ring', (await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle)) !== 'none');
  if (shotDir) await page.screenshot({ path: path.join(shotDir, 'smoke.png'), fullPage: true });

  const mobile = await browser.newPage({ viewport: { width: 375, height: 700 } });
  await mobile.goto(url);
  check('no horizontal scroll at 375px', !(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth)));
  check('no page errors', errors.length === 0, errors.join('; '));
  await browser.close();

  for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.detail ? `  (${r.detail})` : ''}`);
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})();
