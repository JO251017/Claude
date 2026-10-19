# dev_log

## A. 읽기 전용 점검 (2026-10-19)
- 저장소 구조: `index.html`, `app.js`, `style.css`(JS 리마인더 앱), `.claude/skills/design-taste-frontend`, `skills-lock.json`. Python 코드·테스트·docs 없음.
- 기존 M1 코드 위치: **없음**. 기존 테스트: **없음**(pytest 미설치 상태였고 pip로 설치). 실행 결과 통과 0 / 실패 0.
- `docs/api/`(HUB 공식 문서): **없음** → HubTrendSource 호출부는 NotImplementedError 스텁.
- 기존 파일은 수정·삭제하지 않음. 이름 충돌 없음.

## 가정
- 가정: 작업 브랜치는 세션 지정 브랜치 `claude/mvp-stage1-profit-candidates-n7v3ie`를 사용한다(별도 `mvp-stage1` 브랜치를 만들지 않음). push 하지 않음.
- 가정: Python 패키지명은 기존 구조가 없어 `src`(`src.common`, `src.discovery`, `src.sourcing`)로 한다. 실행은 `python -m src.cli`.
- 가정: 금액·요율 계산은 `fractions.Fraction`으로 정확 계산(부동소수 올림 오차 방지). 보고용 값만 반올림(half-up).
- 가정: costs.csv에 고객 부담 배송비(F) 칸이 없으므로 F = S(도매 배송비)로 한다.
- 가정: 숫자 칸의 천 단위 쉼표("12,000")는 비숫자로 보고 입력 오류 처리한다(보수적 해석).
- 가정: 최신성 판단에 쓰는 researched_at은 해당 키워드의 시세 표본 중 가장 오래된 날짜다.
- 가정: 성장률 계산 기준월은 `--as-of`(기본 오늘)로 정한다. 샘플은 `--as-of 2026-07-15` 기준으로 만들었다.
- 가정: 성장률 창(최근 3개월, 1년 전 같은 3개월=15개월 중 앞 3개)은 정의 상수로 코드에 두고, 임계값(2.5, 3배, 1.0, 7일, 14일 등)은 모두 config.
- 가정: `.env.example`의 HUB 키 이름(NAVER_HUB_CLIENT_ID/SECRET)은 임시 이름이다. 확인 필요: 실제 HUB 인증 방식은 공식 문서 확인 후 조정.
- 가정: 승인 뷰 approved_candidates는 "실행 승인=승인 AND 항목 O" 둘 다 최신 이벤트 기준으로 충족한 항목만 보여 준다.
- 가정: 승인 가져오기의 중복 방지는 (run_id, scope, 파일 SHA-256) 유일 제약이다. 같은 파일 재가져오기는 0건 기록.
- 가정: 후보 시트=통과·보류(원가/시세 미입력 보류 포함). 탈락·실패 시트=탈락 + 입력 오류 행.
- 가정(중요): 기본 config(margin_min 15%)에서는 T_sug >= T_min 이면 보수 순이익이 항상 0.07×T 이상이라 "보수 시나리오 보류"가 수학적으로 발생하지 않는다(테스트로 확인). 사양끼리의 충돌이지만 중단하지 않고, 샘플 실행에는 margin_min_pct만 낮춘 `data/sample/config.sample.yaml`을 쓴다. 기본 config.yaml은 건드리지 않는다. 보류 분기 자체는 단위 테스트(마진 5% 설정)로 검증한다.
- 가정: 경쟁 시세 행에서 price/shipping이 비어 있거나 비숫자면 그 행을 건너뛴다(shipping 공백을 0으로 채우지 않음).
- 가정: 재시도 백오프는 429는 [1,2,4]초(최대 3회), 5xx·타임아웃은 [1,2]초(최대 2회), 4xx(429 제외)는 재시도 없음. 모두 config.
