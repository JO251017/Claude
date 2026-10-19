# 네이버 검색광고 API - 키워드도구 (공식 문서 요약)
출처(2026-10-19 확인):
- 명세: https://naver.github.io/searchad-apidoc/ (gh-pages `assets/json/ncc-keywordstool.json`)
- 서명·헤더: https://github.com/naver/searchad-apidoc/blob/master/python-sample/examples/signaturehelper.py , ad_management_sample.py
구현: `src/discovery/keyword_finder.py`의 `SearchAdClient`.

- 기본 주소: `https://api.searchad.naver.com` (공식 샘플 BASE_URL)
- 요청: `GET /keywordstool`
  - `hintKeywords`: 힌트 키워드, 쉼표 구분, 최대 5개
  - `showDetail`: 1이면 연관 키워드별 상세 통계(검색수, 클릭수, CTR, 경쟁정도, 노출 깊이)
  - 그 외 siteId, biztpId, event, month (사용 안 함)
- 헤더(공식 샘플): `X-Timestamp`(밀리초), `X-API-KEY`(액세스 라이선스), `X-Customer`(고객 ID), `X-Signature`, `Content-Type: application/json; charset=UTF-8`
- 서명(공식 샘플): `message = "{timestamp}.{method}.{uri}"`, HMAC-SHA256(비밀키, message) → Base64. uri는 쿼리스트링을 뺀 경로(`/keywordstool`).
- 응답 항목(RelKwdStat): `relKeyword`, `monthlyPcQcCnt`, `monthlyMobileQcCnt`(최근 30일 합계, **10 미만이면 문자열 "<10"**), `monthlyAvePcClkCnt`, `monthlyAveMobileClkCnt`, `monthlyAvePcCtr`, `monthlyAveMobileCtr`, `plAvgDepth`, `compIdx`(PC 광고 기준 경쟁정도 low/mid/high)
- 응답 형태: 명세의 응답 스키마 제목이 `keywordList`이고 타입은 배열이다. 구현은 배열 그대로이거나 `{"keywordList": [...]}`인 경우 둘 다 읽는다. 확인 필요: 실제 응답이 어느 쪽인지.
- 확인 필요(문서에 없음): 호출 한도, 힌트 키워드에 띄어쓰기를 허용하는지. 실패하면 해당 씨앗만 "조회 실패"로 표시한다.
- 인증 정보 발급: 검색광고 관리 화면(manage.searchad.naver.com) > 도구 > API 사용 관리에서 라이선스 생성.
