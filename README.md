# 순이익 후보표 도구 (스마트스토어 1단계)

키워드·경쟁 시세·도매 원가·클릭 추이를 넣으면 **팔아서 남는 상품 후보**를 골라 엑셀로 정리해 주는 도구입니다.
네이버 쇼핑 AI가 추천할 때 쓰는 정보(스펙·모델명·출고일·차별점)를 갖췄는지도 함께 점검합니다.

> 순이익은 **세전**(부가세·소득세 미반영)입니다. 요율·기준값은 모두 `config.yaml`에서 바꿉니다.

## 1. 처음 한 번 설치
```
pip install -r requirements.txt
```

## 2. 매번 쓰는 순서
1. `data/templates/`의 양식 4개를 `data/input/`에 복사해 채웁니다.

   | 파일 | 내용 |
   |---|---|
   | `keywords.csv` | 검토할 키워드 |
   | `competitors.csv` | 경쟁 판매자 가격·배송비·조사일 |
   | `costs.csv` | 도매 원가·배송비·도매처 + AI 노출 정보 4칸 |
   | `trends.csv` | 네이버 데이터랩 쇼핑인사이트의 월별 클릭 추이(최근 15개월, 이번 달 제외) |

2. 실행합니다.
   ```
   python -m src.cli run
   ```
   `output/candidates_<실행번호>.xlsx`가 생깁니다.

3. 엑셀을 열어 확인하고 승인합니다.
   - **요약** 시트: 한 줄 결론, 근거, 이상 징후. 맨 아래 `실행 승인`에 승인/반려/보류를 고르세요.
   - **후보** 시트: 통과·보류 후보. 맨 오른쪽 `항목 승인(O/X)`에 O 또는 X.
   - **탈락·실패** 시트: 탈락 이유와 모자란 금액.

4. 저장한 엑셀을 가져옵니다(같은 파일을 두 번 가져와도 중복 기록되지 않음).
   ```
   python -m src.cli approve import output/candidates_<실행번호>.xlsx
   ```
   실행 승인 = 승인이고 항목이 O인 것만 "승인된 후보"로 남습니다.

## 3. 판정 기준 (탈락 > 보류 > 통과 순으로 더 나쁜 쪽)
| 판정 | 언제 |
|---|---|
| 탈락 | 시장 가격으로 팔면 최소 마진(15%)·최소 이익(2,000원)을 못 맞춤 / 고객 배송비가 시장가 이상 |
| 보류 | 원가·시세 미입력, 조사일이 오래됨(시세 7일·원가 14일 초과), 클릭 추이 확인 불가 |
| 통과 | 위에 해당 없음 |

경고(판정에는 영향 없음): 배송비 비중 과다, 수량당 배송비, 표본 부족, 계절성·급등 표시.

### AI 노출 준비 (후보 시트 `AI 노출 준비` 칸)
네이버 쇼핑 AI 에이전트는 상품 스펙·후기·도착 예정일을 근거로 추천합니다(2026 보도). 그래서 후보 단계에서 아래 4가지를 갖췄는지 봅니다.
`spec_info`(스펙을 글로 받을 수 있으면 Y), `model_name`, `dispatch_days`(출고 일수), `differentiator`(차별점).
- 기본은 **표시만** 합니다. 판정에도 반영하려면 `config.yaml`의 `ai_readiness.affects_verdict: true`.
- 리뷰는 판매 후에 쌓이므로 이 단계에서는 보지 않습니다.

## 4. 연습용 샘플
가상 데이터로 결과를 미리 볼 수 있습니다.
```
python -m src.cli --config data/sample/config.sample.yaml run --keywords data/sample/keywords.csv --competitors data/sample/competitors.csv --costs data/sample/costs.csv --trends data/sample/trends.csv --as-of 2026-07-15
```
(샘플 설정은 보류 사례를 보여 주려고 최소 마진만 5%로 낮춘 것입니다. 실제로는 `config.yaml`을 씁니다.)

## 5. 알아둘 점
- `data/input/`, `output/`은 git에 올라가지 않습니다(개인 데이터 보호).
- 클릭 추이는 지금 `trends.csv`로 직접 넣습니다. 네이버 API 자동 조회는 공식 문서가 필요해 아직 꺼져 있습니다(`docs/RUN_REAL_API.md`).
- 실행 기록: `output/logs/`, 알림 기록: `output/notifications.log`, 데이터: `output/mvp.db`.
- 개발 기록과 가정: `docs/dev_log.md`.

## 6. 개발자용
```
python -m pytest -q
```
