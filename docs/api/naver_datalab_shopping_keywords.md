# 네이버 데이터랩 쇼핑인사이트 API - 키워드별 트렌드 조회 (공식 문서 요약)
출처: https://developers.naver.com/docs/serviceapi/datalab/shopping/shopping.md (2026-10-19 확인)
구현: `src/discovery/trends.py`의 `DatalabTrendSource`. 이 문서에 없는 동작은 구현하지 않았다.

- 요청: `POST https://openapi.naver.com/v1/datalab/shopping/category/keywords`, HTTPS, JSON 본문
- 헤더: `X-Naver-Client-Id`, `X-Naver-Client-Secret`(개발자센터 애플리케이션 등록 시 발급), `Content-Type: application/json`
- 비로그인 방식 오픈 API. **하루 호출 한도 1,000회.**

| 파라미터 | 필수 | 설명 |
|---|---|---|
| startDate | Y | yyyy-mm-dd. 2017-08-01부터 |
| endDate | Y | yyyy-mm-dd |
| timeUnit | Y | date / week / month |
| category | Y | 쇼핑 분야 코드. 네이버쇼핑에서 카테고리 선택 시 URL의 `cat_id` 값 |
| keyword | Y | `[{"name": 그룹명, "param": [검색어 1개]}]`, 최대 5쌍 |
| device, gender, ages | N | 미설정 시 전체 |

- 응답: `results[].title`, `results[].keyword`, `results[].data[].period`(구간 시작일 yyyy-mm-dd), `results[].data[].ratio`(구간별 클릭량 상대 비율, **결과 중 가장 큰 값을 100으로 둔 상대값**)
- 오류: 400 잘못된 요청 / 500 서버 내부 오류 / 403 API 권한 없음(애플리케이션에 API 사용 설정 안 함)
