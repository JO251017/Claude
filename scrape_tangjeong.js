const { chromium } = require('playwright');

const SUPPLY_PRICE = {
  '84A': 45900,
  '84B': 44900,
  '84C': 43900,
};

function formatPrice(manwon) {
  if (!manwon) return '-';
  const eok = Math.floor(manwon / 10000);
  const rem = manwon % 10000;
  if (rem === 0) return `${eok}억`;
  return `${eok}억 ${rem.toLocaleString()}만`;
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/opt/pw-browsers/chromium',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });

  const results = [];

  // 1. 아실 사이트 시도
  try {
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36');
    
    console.log('=== [1] 아실 조회 ===');
    await page.goto('https://asil.kr/asil/search.jsp?keyword=%ED%83%95%EC%A0%95%ED%91%B8%EB%A5%B4%EC%A7%80%EC%98%A4%EC%84%BC%ED%84%B0%ED%8C%8C%ED%81%AC', {
      waitUntil: 'networkidle', timeout: 30000
    });
    await page.waitForTimeout(3000);
    
    const title = await page.title();
    const url = page.url();
    console.log('제목:', title);
    console.log('URL:', url);
    
    // 검색 결과 링크 확인
    const links = await page.$$eval('a', els => els.map(e => ({text: e.textContent?.trim(), href: e.href})).filter(l => l.text && l.text.length > 2));
    const relevant = links.filter(l => l.text.includes('탕정') || l.text.includes('푸르지오'));
    console.log('관련 링크:', JSON.stringify(relevant.slice(0, 5)));
    
    await page.screenshot({ path: '/tmp/claude-0/-home-user-Claude/8191288c-d12a-5528-a45c-350871a767c2/scratchpad/asil.png' });
    await page.close();
  } catch(e) {
    console.log('아실 오류:', e.message);
  }

  // 2. 호갱노노 시도
  try {
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36');
    
    console.log('\n=== [2] 호갱노노 조회 ===');
    await page.goto('https://hogangnono.com/apt/search?q=%ED%83%95%EC%A0%95%ED%91%B8%EB%A5%B4%EC%A7%80%EC%98%A4%EC%84%BC%ED%84%B0%ED%8C%8C%ED%81%AC', {
      waitUntil: 'networkidle', timeout: 30000
    });
    await page.waitForTimeout(3000);
    
    console.log('URL:', page.url());
    console.log('제목:', await page.title());
    
    const text = await page.evaluate(() => document.body.innerText);
    const lines = text.split('\n').filter(l => l.includes('탕정') || l.includes('푸르지오') || l.includes('센터파크'));
    console.log('관련 텍스트:', lines.slice(0, 10).join('\n'));
    
    await page.screenshot({ path: '/tmp/claude-0/-home-user-Claude/8191288c-d12a-5528-a45c-350871a767c2/scratchpad/hogangnono.png' });
    await page.close();
  } catch(e) {
    console.log('호갱노노 오류:', e.message);
  }

  // 3. 국토부 실거래가 공개시스템 (분양권 탭)
  try {
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36');
    
    console.log('\n=== [3] 국토부 실거래가 시스템 ===');
    await page.goto('https://rt.molit.go.kr/', {
      waitUntil: 'networkidle', timeout: 30000
    });
    await page.waitForTimeout(2000);
    console.log('URL:', page.url());
    console.log('제목:', await page.title());
    await page.screenshot({ path: '/tmp/claude-0/-home-user-Claude/8191288c-d12a-5528-a45c-350871a767c2/scratchpad/molit.png' });
    await page.close();
  } catch(e) {
    console.log('국토부 오류:', e.message);
  }

  // 4. 직방 분양 검색
  try {
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36');
    
    console.log('\n=== [4] 직방 분양권 조회 ===');
    await page.goto('https://www.zigbang.com/home/apt/search?q=%ED%83%95%EC%A0%95%ED%91%B8%EB%A5%B4%EC%A7%80%EC%98%A4', {
      waitUntil: 'networkidle', timeout: 30000
    });
    await page.waitForTimeout(2000);
    console.log('URL:', page.url());
    console.log('제목:', await page.title());
    await page.close();
  } catch(e) {
    console.log('직방 오류:', e.message);
  }

  await browser.close();
  console.log('\n크롤링 완료');
}

main().catch(console.error);
