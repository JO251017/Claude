# 네이버 검색 API - 쇼핑 검색 (공식 문서 요약)
출처: https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md (2026-10-19 확인)
구현: `src/discovery/keyword_finder.py`의 `ShopSearchClient` (키워드별 상품 수만 사용).

- 요청: `GET https://openapi.naver.com/v1/search/shop.json?query=...&display=..`
  - `query`(필수, UTF-8), `display`(1~100, 기본 10), `start`(1~1000), `sort`(sim/date/asc/dsc), `filter`, `exclude`
- 헤더: `X-Naver-Client-Id`, `X-Naver-Client-Secret` (데이터랩과 같은 개발자센터 앱, **API 설정에서 '검색' 선택 필요**)
- **하루 호출 한도 25,000회.**
- 응답(JSON): `total`(총 검색 결과 개수), `start`, `display`, `items[]`(title, link, image, lprice, hprice, mallName, productId, productType, maker, brand, category1~4)
- 오류: 400(SE01~SE04, SE06 잘못된 요청), 404(SE05), 500(SE99), 403(API 권한 없음 - 앱에 '검색' 미선택)
