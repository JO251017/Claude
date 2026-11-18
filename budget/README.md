# 모모 가계부 (AI 스마트 가계부)

기록을 놓쳐도 쉽게 다시 시작하는 모바일 중심 웹 가계부. 의존성 없음 (Node 18+ 만 필요).

## 실행

```bash
cd budget
cp .env.example .env   # GEMINI_API_KEY 입력 (없으면 AI 없이 로컬 기능으로 동작)
node server.js         # http://localhost:8787
```

## 구조

| 파일 | 역할 |
|---|---|
| `server.js` | 정적 파일 + Gemini 프록시(`/api/parse`, `/api/ocr`, `/api/chat`, `/api/status`). API 키는 서버 환경변수에만 존재 |
| `public/js/core.js` | 데이터 구조, 저장/자동 백업, 통계·예산·누락 탐지·캐릭터 계산 (모든 금액 계산) |
| `public/js/nlp.js` | 로컬 자연어 해석기 ("어제 김밥 8천원") — AI 없이도 동작 |
| `public/js/charts.js` | SVG 차트, 마스코트 |
| `public/js/app.js` | 화면: 홈 / 내역(달력 복구) / 통계 / AI 코치 / 모모 |

## 원칙 구현 위치

- **AI 추측은 저장하지 않음**: AI·로컬 해석 결과는 모두 미리보기 → 사용자 승인 후 저장. 금액·날짜가 불확실하면 체크박스가 잠기고 수정 또는 "맞아요" 확인이 필요.
- **중복 방지**: 같은 날짜·금액·유형 + 비슷한 사용처면 중복 후보로 표시, 기본 해제.
- **누락 복구**: 기록이 없는 날을 "확인 필요"로만 표시. "지출 없음"으로 확인하면 다시 묻지 않음. 여러 날짜 일괄 입력.
- **계산은 코드로**: AI에는 앱이 계산한 집계값만 전달하고, 숫자를 새로 만들지 말라고 지시.
- **보상 구조**: XP는 하루 1회 기록, 예산 준수 달(그 달 70% 이상 기록 시), 미션, 저축 목표 달성에만 지급. 지출 금액·건수와 무관.
- **개인정보**: 거래 기록은 브라우저(localStorage)에만 저장. 이미지는 서버 메모리에서 분석 후 폐기, 요청 본문은 로그에 남기지 않음.

## 데이터 (localStorage `momo-budget-v1`)

`profile`, `transactions[{id,date,time,type,amount,category,merchant,memo,source}]`, `categories`, `budgets{YYYY-MM:{total,byCategory}}`, `goals[{deposits[]}]`, `dayChecks{date:'nospend'|'ok'}`, `character`, `aiReports`, `uploads`(이미지 미보관), `meta`.
백업: 하루 1회 자동 사본(`momo-budget-v1-autobackup`) + 설정에서 JSON 내보내기/불러오기.

## 비용·제한

- Gemini 무료 등급은 Flash 계열 위주이며 분당·일일 한도가 낮음(정확한 수치는 [공식 페이지](https://ai.google.dev/pricing)에서 확인 필요). 서버는 기본 분당 5회·하루 100회로 제한.
- 무료 등급 입력 데이터는 Google 약관에 따라 서비스 개선에 쓰일 수 있음. 민감하면 유료 등급 사용 검토.
- 음성 입력은 브라우저 Web Speech API (Chrome은 음성을 Google 서버에서 처리).

## 알려진 한계

- 데이터가 기기별 브라우저에 저장됨 → 기기 간 동기화 없음(다음 단계: Supabase/Firestore 무료 등급 + 로그인).
- 로컬 자연어 해석기는 규칙 기반이라 복잡한 문장은 AI 해석이 더 정확함.
