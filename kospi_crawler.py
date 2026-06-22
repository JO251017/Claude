from playwright.sync_api import sync_playwright

def crawl_kospi_top10():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("네이버 금융 코스피 시가총액 상위 종목 크롤링 중...\n")
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

            name = name_el.inner_text().strip()
            price     = cols[1].inner_text().strip()
            change_rt = cols[3].inner_text().strip()
            market_cap= cols[6].inner_text().strip()
            per       = cols[9].inner_text().strip()

            results.append({
                "종목명": name,
                "현재가": price,
                "등락률": change_rt,
                "시가총액(억)": market_cap,
                "PER": per,
            })

            if len(results) >= 10:
                break

        browser.close()

        print(f"{'순위':<4} {'종목명':<14} {'현재가':>10} {'등락률':>8} {'시가총액(억)':>14} {'PER':>8}")
        print("-" * 64)
        for i, r in enumerate(results, 1):
            print(f"{i:<4} {r['종목명']:<14} {r['현재가']:>10} {r['등락률']:>8} {r['시가총액(억)']:>14} {r['PER']:>8}")

crawl_kospi_top10()
