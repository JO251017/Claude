const { chromium } = require('playwright');

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/opt/pw-browsers/chromium',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });

  const SCRATCHPAD = '/tmp/claude-0/-home-user-Claude/8191288c-d12a-5528-a45c-350871a767c2/scratchpad';

  // 1. 아실 시도
  try {
    const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36' });
    const page = await ctx.newPage();
    
    console.log('=== [1] 아실 조회 ===');
    await page.goto('https://asil.kr/asil/search.jsp?keyword=%ED%83%95%EC%A0%95%ED%91%B8%EB%A5%B4%EC%A7%80%EC%98%A4%EC%84%BC%ED%84%B0%ED%8C%8C%ED%81%AC', {
      waitUntil: 'networkidle', timeout: 30000
    });
    await page.waitForTimeout(3000);
    console.log('URL:', page.url());
    console.log('제목:', await page.title());
    const text = await page.evaluate(() => document.body.innerText);
    const lines = text.split('\n').filter(l => l.trim().length > 0).slice(0, 30);
    console.log('내용 일부:\n', lines.join('\n'));
    await page.screenshot({ path: `${SCRATCHPAD}/asil.png` });
    await ctx.close();
  } catch(e) {
    console.log('아실 오류:', e.message);
  }

  // 2. 국토부 실거래가 분양권 API (공개 데이터)
  try {
    const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36' });
    const page = await ctx.newPage();
    
    console.log('\n=== [2] 공공데이터 API 조회 (분양권) ===');
    // 인증키 없이 시도
    const url = 'https://apis.data.go.kr/1613000/RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade?serviceKey=SAMPLE&LAWD_CD=44200&DEAL_YMD=202506&numOfRows=100&pageNo=1';
    await page.goto(url, { timeout: 10000 });
    const content = await page.content();
    console.log('API 응답:', content.substring(0, 500));
    await ctx.close();
  } catch(e) {
    console.log('API 오류:', e.message);
  }

  // 3. 호갱노노
  try {
    const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36' });
    const page = await ctx.newPage();
    
    console.log('\n=== [3] 호갱노노 조회 ===');
    await page.goto('https://hogangnono.com/', { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.waitForTimeout(2000);
    
    // 검색창
    const input = await page.$('input[type="text"], input[placeholder]');
    if (input) {
      await input.fill('탕정푸르지오센터파크');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(3000);
    }
    console.log('URL:', page.url());
    const text = await page.evaluate(() => document.body.innerText);
    const lines = text.split('\n').filter(l => l.includes('탕정') || l.includes('푸르지오') || l.includes('센터파크'));
    console.log('관련 텍스트:', lines.slice(0, 10).join('\n'));
    await page.screenshot({ path: `${SCRATCHPAD}/hogangnono.png` });
    await ctx.close();
  } catch(e) {
    console.log('호갱노노 오류:', e.message);
  }

  await browser.close();
}

main().catch(console.error);
