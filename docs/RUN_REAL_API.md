# 실제 쇼핑인사이트(NAVER API HUB) 1회 검증 절차

> 현재 상태: `HubTrendSource.fetch`는 **NotImplementedError 스텁**이다. 저장소에 `docs/api/`(HUB 공식 문서)가 없어 규격을 추측해 구현하지 않았다.
> 따라서 아래 절차의 3단계 이후는 **먼저 `docs/api/`에 공식 문서를 넣고 `src/discovery/trends.py`의 `HubTrendSource`를 구현한 뒤** 진행할 수 있다. 재시도(429 Retry-After, 5xx·타임아웃)와 호출 간격(0.2초)은 `RetryingTrendSource`에 이미 적용되어 있으므로, 구현 시 HTTP 오류를 `HttpError(status, retry_after)`, 타임아웃을 `TimeoutError`로 던지고, 응답 원문·헤더는 로그에 남기지 않는다.

## 1. 키 설정 (값은 어디에도 커밋하지 않는다)
1. `.env.example`을 `.env`로 복사한다(`.env`는 `.gitignore` 대상).
2. `.env`에 아래 **키 이름**에 해당하는 값을 직접 채운다.
   - `NAVER_HUB_CLIENT_ID`
   - `NAVER_HUB_CLIENT_SECRET`
   - 확인 필요: 이 이름은 임시다. 공식 문서의 인증 방식에 맞게 `.env.example`과 `config.yaml`의 `hub.required_env`를 함께 고친다.

## 2. 이용약관 확인
- HUB 이용약관·데이터 이용 조건을 확인한 뒤 `config.yaml`의 `hub.api_terms_ack`를 `true`로 바꾼다. `false`면 `--source hub` 실행이 시작 전에 중단된다.

## 3. 실행 (키워드 3~5개 소량)
```
python -m src.cli run --source hub \
  --keywords data/input/keywords.csv --competitors data/input/competitors.csv --costs data/input/costs.csv
```
- 키가 없으면 누락된 **키 이름만** 출력하고 중단된다. 결과는 `output/candidates_<run_id>.xlsx`, 로그는 `output/logs/run_<run_id>.log`.
- 로그·DB·엑셀에 ratio 시계열이 남지 않는지 확인한다(파생값만 저장: 성장률, 플래그, 조회시각, 소스명).

## 4. 쇼핑인사이트 화면과 성장률 대조 (3개 표본)
키워드 3개를 골라 아래 표를 채운다. 쇼핑인사이트 화면에서 같은 기간·같은 설정(분야/기기/성별/연령)으로 월별 값을 확인한다.

| 키워드 | 최근 3개월 월별 값 | 1년 전 같은 3개월 월별 값 | 수기 G = 평균(최근3)/평균(1년전3) − 1 | 엑셀 클릭 증가율 | 일치(±0.1%p) |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |

- 최근 15개 완결 월(이번 달 제외)을 쓰므로, 화면의 기간도 이번 달을 제외한 직전 15개월로 맞춘다.
- 1년 전 평균이 `growth_min_base`(기본 1.0) 미만이거나 필요한 6개 월 중 결측이 있으면 엑셀에 "미확인"으로 나오는 것이 정상이다.
- 불일치 시: 기간 정렬(월 경계), ratio 기준(상대값 정규화), 분야/기기 설정 차이부터 확인한다.

## 5. 정리
- 대조 결과(3건)와 실제 호출 횟수·한도 상태를 `docs/dev_log.md`에 기록한다.
- 키 값은 어떤 파일·로그·채팅에도 붙여넣지 않는다.
