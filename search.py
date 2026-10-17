from playwright.sync_api import sync_playwright

def search_google(query):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.google.com")
        page.fill('textarea[name="q"]', query)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")

        results = page.query_selector_all("div.g")
        for i, result in enumerate(results[:5], 1):
            title = result.query_selector("h3")
            link = result.query_selector("a")
            desc = result.query_selector("div[style='-webkit-line-clamp:2']")

            print(f"\n[{i}]")
            print("제목:", title.inner_text() if title else "없음")
            print("링크:", link.get_attribute("href") if link else "없음")
            print("설명:", desc.inner_text() if desc else "없음")

        browser.close()

query = input("검색어 입력: ")
search_google(query)
