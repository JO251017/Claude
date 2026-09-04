# SaveMap Backend

하이퍼로컬 절약 데이터 통합·검증 플랫폼 (MVP Phase 1 · 평택·천안·아산).

자세한 설계는 [ARCHITECTURE.md](./ARCHITECTURE.md) 참고.

## 빠른 시작 (로컬)

```bash
cp .env.example .env          # 키 채우기 (KAKAO/DATA_GO_KR/GEMINI ...)
docker compose up -d db redis
pip install -e ".[dev]"
alembic upgrade head          # postgis 확장 + 테이블 생성
uvicorn app.main:app --reload
```

- API 문서: http://localhost:8000/docs
- 헬스체크: http://localhost:8000/health

## 배포 (Render)

리포 루트의 `render.yaml`(Blueprint)로 웹 서비스 + Redis를 한 번에 배포합니다.

1. https://render.com 가입 (GitHub 계정으로 로그인 권장)
2. 대시보드 → "New" → "Blueprint" → 이 GitHub 저장소 선택
3. `render.yaml`을 자동으로 인식 → "Apply" 클릭
4. `savemap-api` 서비스의 **Environment** 탭에서 `sync: false`로 표시된 값들을 직접 입력:
   - `SUPABASE_DB_URL`, `SUPABASE_JWT_SECRET`
   - `KAKAO_REST_API_KEY`, `DATA_GO_KR_KEY`, `TOUR_API_KEY`, `OPINET_API_KEY`
   - `GEMINI_API_KEY`
   - (선택) `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
5. 배포 완료되면 제공되는 `https://savemap-api-xxxx.onrender.com` 주소로 접속

무료 플랜은 트래픽이 없으면 슬립 상태로 전환되어, 첫 요청 시 기동에 몇십 초 걸릴 수 있습니다.

## 테스트

```bash
pytest                        # 순수 단위테스트 (DB 불필요)
```

핵심 검증 대상: `savings_calculator`(절약 계산), `ranker`(정렬), `dedupe`(소스 우선순위 병합),
`validate`(레이어별 유효성), `scoring`(신뢰도 재계산).

## 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/v1/search` | 반경 내 절약 검색 (Rule-based) |
| POST | `/v1/reports` | 사진 제보 (image_url 필수) |
| POST | `/v1/verifications` | 팩트체크 → 신뢰도 재계산 |
| POST | `/v1/merchant/offers` | 사업자 등록 (후속) |

## 구현 상태

- ✅ 도메인 모델 · 마이그레이션 · 공통 파이프라인 · 검색엔진 · 검색/제보/검증 API
- 🔶 외부 API 어댑터 (Kakao 지오코딩 외 — 실제 스펙 확인 후 구현, `NotImplementedError` 표시)
- 🔶 Layer3 실시간 · AI 동선 추천 · 게이미피케이션 (인터페이스 스텁)
