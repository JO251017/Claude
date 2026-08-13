# SaveMap 아키텍처 (MVP Phase 1)

SaveMap = 하이퍼로컬 절약 정보를 **수집 → 정제 → 검증 → 공간질의**로 재구성하는
데이터 통합·검증 플랫폼. 크롤러가 아니라 파이프라인 제품이다.

## 기술 스택
- DB: **Supabase 관리형 PostgreSQL 16 + PostGIS 3.4** (공간 인덱스 GiST 주, H3 res9 보조)
- API: **FastAPI (Python 3.12)**, 서비스 간 REST
- 비동기 배치: **Celery + Redis broker**
- 캐시/TTL: **Redis** (Layer3 휘발성 데이터 전용)
- 외부 연동: Kakao Maps(지오코딩/길찾기), 공공데이터포털·TourAPI·오피넷, Gemini Vision(OCR), Supabase Storage

## 데이터 소스 (우선순위 순)
| | 소스 | 방식 | Layer |
|---|---|---|---|
| S1 | 공공 API | 배치 스케줄링 + 캐시 | Core Base |
| S2 | 파트너 API | OAuth2·RateLimit·서킷브레이커 | Regular |
| S3 | 사업자 콘솔 | 실시간 인덱싱, CRUD | Regular/Flash |
| S4 | 사용자 제보 | 이미지 → OCR → 위치 → AI분류 | Flash |
| S5 | 사용자 검증 | 팩트체크 → 신뢰도 재계산 (+XP) | — |

## 3-레이어 휘발성 모델
- **Core Base** (공공/무료): 월1회 배치, Redis 캐시
- **Regular** (상시할인/지역화폐): 주1회, `expires_at` 만료 관리
- **Flash** (마감임박/타임세일): 실시간, Redis TTL + 카운트다운 (MVP에서는 제보 탭만)

## 모듈 구조
```
app/
  core/          설정·DB·Redis·Celery·공간헬퍼·에러코드
  integrations/  외부 API 클라이언트 (kakao/gov_data/gemini/supabase_storage)
  domain/        SQLAlchemy 모델 + enum
  sources/       S1~S5 수집 모듈 (도메인 경계)
  ingestion/     공통 파이프라인 (normalize→validate→dedupe→upsert)
  engine/        검색엔진 (spatial_query→rule_filter→benefit_combiner→savings_calculator→ranker)
  gamification/  XP 서비스 (길드·랭킹은 후속)
  api/v1/        엔드포인트 (search/reports/verifications/merchant)
```
**경계 원칙**: `sources`(수집)와 `engine`+`api`(질의)를 분리. 외부 API는 `integrations` 경유. `engine`/`api`는 `domain`만 읽는다.

## 절약 검색 흐름
```
GET /v1/search?lat&lng&radius_km&category&payment_methods
 → spatial_query   ① 반경 N km GiST ST_DWithin
 → rule_filter     Layer1+2 후보 (MVP)
 → benefit_combiner ②공공 무료혜택 ③보유 결제수단 혜택 조합
 → savings_calculator  실제 낼 돈 = 기본가 − 매장할인 − 카드/통신 − 지역화폐
 → ranker          ④ 절약률(%) × 신뢰도 정렬
```

## AI 절약 플랜 흐름 (동선 추천)
개별 매장을 나열만 하는 것과 별개로, 예산을 넣으면 실제 후보 중에서 예산 안에
들어오는 코스를 짜서 "총 얼마 절약"을 구체적으로 보여주는 기능 (2026-08-12 구현).

**Activity(무엇을 할까) / OfferType(어떻게 절약할까) 분리 (2026-08-13):** 사용자는
`할인/무료/마감세일`(=`Category`, 절약 수단) 을 직접 고르지 않는다 — "식사/커피/
디저트" 같은 `RouteActivity`를 고르면, `Category`는 SaveMap이 내부적으로 자동
탐색한다(`rank_candidates`가 점수로 우선순위를 매김). `RouteActivity`는 새 컬럼 없이
`Place.category_name`(공공데이터/카카오가 준 실제 업종 문자열)을 키워드로 해석해서
얻는다(`app/engine/activity_classifier.py`) — 매핑 근거가 없는 카테고리는 정직하게
미분류(`None`)로 두고, 활동을 지정하면 미분류 매장은 결과에서 빠진다. "쇼핑/문화·
여가/가족활동"은 지금 데이터 소스(일반음식점·휴게음식점·유흥주점 인허가 + 착한가격
업소, 전부 음식점·카페 계열)로는 매핑 근거가 없어 아직 넣지 않았다 — 카카오 로컬
API로 다른 업종을 더 들여오거나 사업자 직접등록이 늘면 다음 후보.
**Context/Constraint 그룹화 (2026-08-13):** "SaveMap 구조 재설계 제안서" §3의 진단 —
Activity/Preference는 이미 별도 개념으로 분리돼 있는데 "누구와/얼마나" 같은 Context와
"반드시 지켜야 하는 조건"인 Constraint는 요청에 flat하게 흩어져 있어 이름조차 없었다.
새 기능 없이 필드만 `RouteContext`(`party_size`)/`RouteConstraints`(`budget`,
`radius_km`, `free_parking_required`)로 묶었다 — 동행/이동수단/시간대처럼 Context가
늘어날 자리를 지금 미리 만들어 둔 것.
```
POST /v1/route/suggest
  {lat, lng, activities?, preference?,
   context: {party_size}, constraints: {budget, radius_km?, free_parking_required?}}
 → spatial_query + rule_filter(activities로 Place.category_name 기반 필터 추가)
   + candidate_builder (검색과 동일 파이프라인 재사용)
 → rank_candidates → dedupe_by_place
 → (preference가 verified/recent면 후보 풀에 실제 trust_score/last_verified_at을
   배치 조회로 채운다 — 안 그러면 전부 기본값이라 정렬이 무의미해짐)
 → route_planner.build_route(preference?)  결정론적 그리디 예산-맞춤 선택. preference
   가 있으면 "어떤 후보부터 담을지" 순서만 바꾼다(가격/신뢰도/최신성/거리, 전부 실측
   값 기준) — 다양성 우선 → 남은 예산/슬롯 채우기 2단계 구조 자체는 그대로. 숫자는
   전부 여기서 계산 — LLM은 관여하지 않음
 → route_planner.generate_summary()  이미 계산된 코스를 Gemini가 문장으로만 설명.
   사용자가 고른 활동/조건은 "왜 이 코스인지" 설명 근거로만 프롬프트에 곁들여지고
   숫자 계산에는 쓰이지 않는다(실패/미설정 시 결정론적 템플릿 문장으로 대체)
```
`free_parking_required`는 유일한 하드 필터다 — `Category.FREE_PARKING`을 그대로
재사용한다. 오퍼 하나는 카테고리가 하나뿐이라(도메인 제약), "식사 오퍼이면서
곁다리로 무료주차도 있음" 같은 조합은 지금 데이터 모델로는 표현할 수 없다(알려진
v1 한계) — 결과가 적게 나올 수 있지만, 없는 걸 있다고 지어내지는 않는다.

## 절대 제약 (설계 반영)
1. 경쟁사·C2C 직접 크롤링 없음 — 당근/뽐뿌/알구몬은 전부 `user_report`(사용자 제보)로만 유입
2. 제보는 이미지에서 시작 — `user_report.image_url` NOT NULL
3. 개인정보 원본 저장 금지 — `payment_method_derived`는 파생 지표(보유여부/등급)만
4. 존재하지 않는 공공 API를 지어내지 않음 — 어댑터는 인터페이스 골격, 실제 엔드포인트/필드 미기입

## 후속 (스텁만 존재)
- Layer3 실시간 Flash Deals 완전 활성화
- 게이미피케이션 (`gamification/` — 길드/랭킹보드/절약 던전 인증)
- AI 절약 플랜의 목적(purpose)/시간대(time window) 입력 — `Place`/`Offer`에 영업시간
  데이터가 아직 없어 v1은 예산/인원만 받는다
