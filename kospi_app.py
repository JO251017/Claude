from flask import Flask, render_template_string
from playwright.sync_api import sync_playwright

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KOSPI 시가총액 TOP 10</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', sans-serif;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    min-height: 100vh;
    padding: 40px 20px;
  }
  .container { max-width: 900px; margin: 0 auto; }
  header {
    text-align: center;
    margin-bottom: 36px;
  }
  header h1 {
    font-size: 2.2rem;
    color: #fff;
    letter-spacing: 2px;
    text-shadow: 0 0 20px rgba(100,200,255,0.4);
  }
  header p {
    color: #aaa;
    margin-top: 6px;
    font-size: 0.9rem;
  }
  .badge {
    display: inline-block;
    background: rgba(100,200,255,0.15);
    border: 1px solid rgba(100,200,255,0.3);
    color: #64c8ff;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.8rem;
    margin-top: 10px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    background: rgba(255,255,255,0.04);
    border-radius: 16px;
    overflow: hidden;
    backdrop-filter: blur(10px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  thead tr {
    background: rgba(100,200,255,0.1);
    border-bottom: 1px solid rgba(100,200,255,0.2);
  }
  thead th {
    padding: 16px 20px;
    color: #64c8ff;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 1px;
    text-align: right;
  }
  thead th:first-child,
  thead th:nth-child(2) { text-align: left; }
  tbody tr {
    border-bottom: 1px solid rgba(255,255,255,0.05);
    transition: background 0.2s;
  }
  tbody tr:hover { background: rgba(100,200,255,0.06); }
  tbody tr:last-child { border-bottom: none; }
  td {
    padding: 14px 20px;
    color: #ddd;
    font-size: 0.95rem;
    text-align: right;
  }
  td:first-child { text-align: left; }
  td:nth-child(2) { text-align: left; }
  .rank {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px; height: 28px;
    border-radius: 50%;
    font-size: 0.8rem;
    font-weight: bold;
  }
  .rank-1 { background: gold; color: #000; }
  .rank-2 { background: silver; color: #000; }
  .rank-3 { background: #cd7f32; color: #fff; }
  .rank-n { background: rgba(255,255,255,0.1); color: #aaa; }
  .name { font-weight: 600; color: #fff; }
  .price { font-weight: 600; color: #fff; font-family: monospace; }
  .up   { color: #ff6b6b; }
  .down { color: #4ecdc4; }
  .cap  { color: #b8b8ff; font-family: monospace; }
  .per  { color: #ffd93d; font-family: monospace; }
  .error-box {
    background: rgba(255,80,80,0.1);
    border: 1px solid rgba(255,80,80,0.3);
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    color: #ff9090;
  }
  footer {
    text-align: center;
    margin-top: 24px;
    color: #555;
    font-size: 0.8rem;
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>📈 KOSPI 시가총액 TOP 10</h1>
    <p>네이버 금융 실시간 데이터</p>
    <span class="badge">{{ updated }}</span>
  </header>

  {% if error %}
  <div class="error-box">
    <p>⚠️ 데이터를 불러오지 못했습니다.</p>
    <p style="margin-top:8px;font-size:0.85rem;">{{ error }}</p>
  </div>
  {% else %}
  <table>
    <thead>
      <tr>
        <th>순위</th>
        <th>종목명</th>
        <th>현재가</th>
        <th>등락률</th>
        <th>시가총액(억)</th>
        <th>PER</th>
      </tr>
    </thead>
    <tbody>
      {% for r in stocks %}
      <tr>
        <td>
          {% if loop.index == 1 %}
            <span class="rank rank-1">1</span>
          {% elif loop.index == 2 %}
            <span class="rank rank-2">2</span>
          {% elif loop.index == 3 %}
            <span class="rank rank-3">3</span>
          {% else %}
            <span class="rank rank-n">{{ loop.index }}</span>
          {% endif %}
        </td>
        <td><span class="name">{{ r.종목명 }}</span></td>
        <td><span class="price">{{ r.현재가 }}</span></td>
        <td><span class="{{ 'up' if '+' in r.등락률 else 'down' }}">{{ r.등락률 }}</span></td>
        <td><span class="cap">{{ r['시가총액(억)'] }}</span></td>
        <td><span class="per">{{ r.PER }}</span></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
  <footer>데이터 출처: 네이버 금융 &nbsp;·&nbsp; Playwright 크롤링</footer>
</div>
</body>
</html>
"""

def crawl():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://finance.naver.com/sise/sise_market_sum.naver?sosok=0")
        page.wait_for_load_state("networkidle")

        rows = page.query_selector_all("table.type_2 tbody tr")
        results = []
        for row in rows:
            cols = row.query_selector_all("td")
            if len(cols) < 10:
                continue
            name_el = row.query_selector("td a.tltle")
            if not name_el:
                continue
            results.append({
                "종목명": name_el.inner_text().strip(),
                "현재가": cols[1].inner_text().strip(),
                "등락률": cols[3].inner_text().strip(),
                "시가총액(억)": cols[6].inner_text().strip(),
                "PER": cols[9].inner_text().strip(),
            })
            if len(results) >= 10:
                break
        browser.close()
        return results

@app.route("/")
def index():
    from datetime import datetime
    try:
        stocks = crawl()
        return render_template_string(HTML,
            stocks=stocks,
            updated=datetime.now().strftime("%Y-%m-%d %H:%M 기준"),
            error=None)
    except Exception as e:
        return render_template_string(HTML, stocks=[], updated="", error=str(e))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
