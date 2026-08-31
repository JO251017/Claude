"""라우트 레벨(HTTP 계층) 테스트 — 실제 DB 없이 conftest.NullSession으로 세션을
갈아끼워서, 요청 검증/인증 거부/응답 스키마 계약이 실제로 지켜지는지 확인한다.
이전에는 이 계층이 사람이 브라우저로 수동 확인하는 것 외엔 자동 검증이 없었다."""


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_deps_reports_db_error_without_crashing(client, monkeypatch):
    # 진짜 DB 연결을 시도하면(샌드박스엔 DB가 없다) OS 기본 타임아웃까지 멈춘다 —
    # 그 자체가 실제 문제였고(db.py에 timeout 추가로 별도 수정), 이 테스트는 그거
    # 말고 "연결 실패해도 500이 아니라 200 + 에러 문자열로 응답하는지"만 본다.
    from app.main import engine

    def _boom(self):
        raise ConnectionError("연결 안 됨 (테스트)")

    # AsyncEngine.connect는 인스턴스 속성이 아니라 읽기 전용 프로퍼티라 인스턴스에는
    # 못 얹고 클래스에 얹어야 한다.
    monkeypatch.setattr(type(engine), "connect", _boom)

    resp = client.get("/health/deps")
    assert resp.status_code == 200
    body = resp.json()
    assert body["db"].startswith("error:")
    assert "redis" in body


def test_search_requires_lat_lng(client):
    resp = client.get("/v1/search")
    assert resp.status_code == 422


def test_search_rejects_radius_out_of_range(client):
    # 반경 검증은 DB 세션에 닿기 전에 일어나야 한다 — NullSession이 쿼리를 막아둔
    # 상태에서도(=DB 호출 없이) 400이 나와야 검증 순서가 맞다는 뜻.
    resp = client.get("/v1/search", params={"lat": 36.99, "lng": 127.11, "radius_km": 999})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "SM4002"


def test_search_rejects_invalid_sort_value(client):
    # 검증은 DB에 닿기 전에 일어나야 한다 — NullSession인 채로 422가 나온다는 것
    # 자체가 sort 파라미터 검증이 쿼리보다 먼저라는 증거.
    resp = client.get("/v1/search", params={"lat": 36.99, "lng": 127.11, "sort": "bogus"})
    assert resp.status_code == 422


def test_search_accepts_every_valid_sort_value(client, monkeypatch):
    # 빈 결과로 짧게 우회해서(DB 없이도) sort 파라미터 자체가 각 유효값을 실제로
    # 통과시키는지만 확인한다 — 빈 place_ids는 카운트 조회들이 전부 자체 단락하므로
    # (get_discover_counts 등) 이 이상 DB를 안 건드린다.
    import app.api.v1.search as search_module

    async def _empty(*_a, **_kw):
        return []

    monkeypatch.setattr(search_module, "query_within_radius", _empty)
    monkeypatch.setattr(search_module, "query_places_without_offer", _empty)
    monkeypatch.setattr(search_module, "discover_nearby_places", _empty)

    for value in ("recommended", "cheapest", "distance", "verified", "recent"):
        resp = client.get("/v1/search", params={"lat": 36.99, "lng": 127.11, "sort": value})
        assert resp.status_code == 200, f"sort={value} 실패: {resp.text}"
        assert resp.json()["results"] == []


def test_route_suggest_rejects_budget_out_of_range(client, monkeypatch):
    from app.core.config import settings

    # 이 테스트는 예산 검증 순서를 확인하는 거라 feature flag는 켜둔다 — 플래그
    # 자체의 동작은 test_route_suggest_disabled_by_default가 따로 확인한다.
    monkeypatch.setattr(settings, "ai_saving_plan_enabled", True)
    # 예산 검증도 DB 세션에 닿기 전에 일어나야 한다 (radius 검증과 같은 순서 원칙).
    resp = client.post(
        "/v1/route/suggest",
        json={"lat": 36.99, "lng": 127.11, "constraints": {"budget": 100}},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "SM4003"


def test_route_suggest_disabled_by_default(client):
    # settings.ai_saving_plan_enabled 기본값은 False — SaveMap vNext 지시서(2026-08-31)
    # "AI Saving Plan = OFF" 요구사항. 예산/반경 검증보다도 먼저 막혀야 한다(DB에
    # 닿기 전, 유효하지 않은 요청이어도).
    resp = client.post(
        "/v1/route/suggest",
        json={"lat": 36.99, "lng": 127.11, "constraints": {"budget": 100}},
    )
    assert resp.status_code == 403
    body = resp.json()["detail"]
    assert body["code"] == "SM4033"
    assert body["enabled"] is False


def test_config_js_reports_ai_saving_plan_flag(client):
    resp = client.get("/config.js")
    assert resp.status_code == 200
    assert "aiSavingPlanEnabled" in resp.text


def test_route_suggest_rejects_invalid_party_size(client):
    resp = client.post(
        "/v1/route/suggest",
        json={
            "lat": 36.99,
            "lng": 127.11,
            "context": {"party_size": 0},
            "constraints": {"budget": 20000},
        },
    )
    assert resp.status_code == 422


def test_route_suggest_rejects_unknown_activity_value(client):
    # activities는 "무엇을 할까요?" 선택지(app.domain.enums.RouteActivity)여야 하고,
    # 예전 offer-type 카테고리 값("discount" 등)을 넣으면 422로 걸러져야 한다 —
    # Activity/Category가 실제로 분리됐는지 검증(사용자 지시, 2026-08-13).
    resp = client.post(
        "/v1/route/suggest",
        json={
            "lat": 36.99,
            "lng": 127.11,
            "activities": ["discount"],
            "constraints": {"budget": 20000},
        },
    )
    assert resp.status_code == 422


def test_route_suggest_rejects_missing_constraints(client):
    # constraints(예산 포함)는 필수 그룹이다 — 아예 안 보내면 422.
    resp = client.post("/v1/route/suggest", json={"lat": 36.99, "lng": 127.11})
    assert resp.status_code == 422


def test_route_suggest_accepts_new_request_shape_before_db(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ai_saving_plan_enabled", True)
    # activities/preference/constraints.free_parking_required가 스키마 레벨에서
    # 통과되는지만 확인한다 — 예산 검증(400) 이전에 422가 나지 않아야 새 필드들이
    # 유효하다는 뜻. context/constraints 그룹화(2026-08-13) 반영.
    resp = client.post(
        "/v1/route/suggest",
        json={
            "lat": 36.99,
            "lng": 127.11,
            "activities": ["dining", "cafe"],
            "preference": "verified",
            "context": {"party_size": 2},
            "constraints": {
                "budget": 100,  # 일부러 범위 밖 값 — 요청 파싱은 통과하고 SM4003으로 걸려야 한다
                "free_parking_required": True,
            },
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "SM4003"


def test_admin_sync_rejects_missing_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.post(
        "/v1/admin/sync/restaurant-registry", params={"category": "일반음식점", "region": "평택시"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_admin_sync_rejects_wrong_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.post(
        "/v1/admin/sync/restaurant-registry",
        params={"category": "일반음식점", "region": "평택시"},
        headers={"X-Admin-Key": "wrong-guess"},
    )
    assert resp.status_code == 401


def test_admin_places_stats_rejects_without_key_before_touching_db(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    # NullSession.execute는 호출되면 NotImplementedError를 던진다 — 401로 먼저
    # 막히면 그 앞에서 끝나야 하므로, 이 테스트가 통과한다는 것 자체가 인증이
    # DB 조회보다 먼저 일어난다는 증거다.
    resp = client.get("/v1/admin/places/stats")
    assert resp.status_code == 401


def test_admin_resync_offers_rejects_without_key_before_touching_db(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.post("/v1/admin/maintenance/resync-offers")
    assert resp.status_code == 401


def test_admin_backfill_offer_blurbs_rejects_without_key_before_touching_db(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.post("/v1/admin/maintenance/backfill-offer-blurbs")
    assert resp.status_code == 401


def test_admin_local_currency_endpoints_reject_without_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    assert client.post("/v1/admin/sync/local-currency-merchants").status_code == 401
    assert client.post("/v1/admin/apply/local-currency-merchants").status_code == 401
    # 업로드 엔드포인트도 파일 파싱 전에 인증으로 먼저 막혀야 한다.
    resp = client.post(
        "/v1/admin/import/local-currency-csv",
        files={"file": ("m.csv", b"garbage", "text/csv")},
    )
    assert resp.status_code == 401


def test_admin_endpoints_disabled_when_key_not_configured(client, monkeypatch):
    from app.core.config import settings

    # 운영에서 ADMIN_SYNC_KEY를 아예 안 넣으면(빈 문자열) 어떤 키를 보내도 거부돼야
    # 한다 — "설정 안 하면 관리자 API 자체가 잠긴다"는 안전장치가 실제로 동작하는지.
    monkeypatch.setattr(settings, "admin_sync_key", "")
    resp = client.get("/v1/admin/places/stats", headers={"X-Admin-Key": ""})
    assert resp.status_code == 401


def test_savings_summary_requires_auth(client):
    # 탐험가 칭호(2026-08-13)를 이 응답에 합쳐 넣었다 — 로그인 없이 호출되면
    # DB 세션에 닿기 전에 401로 걸려야 한다(NullSession이 실행을 막아둔 상태에서도
    # 401이 나면 인증이 먼저라는 뜻, 다른 보호된 엔드포인트들과 동일한 순서 원칙).
    resp = client.get("/v1/users/me/savings-summary")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_merchant_create_place_requires_auth(client):
    resp = client.post(
        "/v1/merchant/places",
        json={"name": "가게", "lat": 36.99, "lng": 127.11},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_merchant_create_place_rejects_invalid_body_with_auth_header_present(client):
    # 인증 헤더가 있어도(값이 유효한 토큰은 아니라 어차피 401이 나지만) lat/lng 같은
    # 필수 필드가 없으면 422로 먼저 걸러지는지까지는 보장하지 않는다 — 여기선 그냥
    # "서버가 500으로 죽지 않는다"만 확인한다(입력 검증 vs 인증 순서는 FastAPI 내부
    # 구현에 따라 달라질 수 있어 강하게 못박지 않음).
    resp = client.post("/v1/merchant/places", json={"name": "가게"})
    assert resp.status_code in (401, 422)


def test_unknown_route_returns_404_not_500(client):
    resp = client.get("/v1/this-route-does-not-exist")
    assert resp.status_code == 404


def test_grant_merchant_verification_requires_admin_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.post("/v1/admin/merchant-verifications", json={"user_id": "user-1"})
    assert resp.status_code == 401


def test_revoke_merchant_verification_requires_admin_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.delete("/v1/admin/merchant-verifications/user-1")
    assert resp.status_code == 401


def test_merchant_status_requires_auth(client):
    resp = client.get("/v1/users/me/merchant-status")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_merchant_route_rejects_authenticated_but_unverified_user(client):
    # 로그인은 됐지만(require_user_id 통과) merchant_verification에 행이 없는
    # 사용자는 403(SM4032)으로 막혀야 한다 — 사업자 콘솔 접근 제어(2-3)가 실제
    # 라우트 의존성 체인에 제대로 물려 있는지 end-to-end로 확인한다.
    from app.api.deps import db_session, require_user_id
    from app.main import app

    class _EmptyVerificationResult:
        def first(self):
            return None

    class _UnverifiedSession:
        async def execute(self, *a, **kw):
            return _EmptyVerificationResult()

    async def _fake_user_id() -> str:
        return "user-unverified"

    async def _fake_db_session():
        yield _UnverifiedSession()

    app.dependency_overrides[require_user_id] = _fake_user_id
    app.dependency_overrides[db_session] = _fake_db_session
    try:
        resp = client.post(
            "/v1/merchant/places",
            json={"name": "가게", "lat": 36.99, "lng": 127.11},
        )
    finally:
        app.dependency_overrides.pop(require_user_id, None)
        app.dependency_overrides.pop(db_session, None)

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "SM4032"


def test_menu_report_analyze_requires_login(client):
    resp = client.post("/v1/places/menu-reports/analyze")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_menu_report_create_requires_login(client):
    resp = client.post("/v1/places/menu-reports", json={})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_menu_report_analyze_does_not_require_merchant_verification(client, monkeypatch):
    # 예전엔 발견된 매장 사진 분석이 사업자 콘솔 전용 엔드포인트(/merchant/menu-items
    # /analyze, RequireMerchantVerifiedDep)를 재사용해서, 사업자 인증 접근 제어(2-3)가
    # 걸리면서 일반 사용자가 막히는 회귀가 생겼었다(사용자 지시, 2026-08-13: "메뉴판
    # 등록은... 사용자들이 등록하도록 바꿔"). /places/menu-reports/analyze는
    # RequireUserDep만 써야 한다 — merchant_route 테스트와 똑같은 "로그인은 됐지만
    # 사업자 인증은 안 된" 오버라이드를 걸어도 403(SM4032)이 나오면 안 된다.
    from unittest.mock import AsyncMock

    from app.api.deps import db_session, require_user_id
    from app.integrations.gemini import GeminiVisionClient
    from app.integrations.supabase_storage import SupabaseStorageClient
    from app.main import app

    class _UnverifiedSession:
        async def execute(self, *a, **kw):
            raise NotImplementedError("analyze는 DB를 안 건드려야 한다")

    async def _fake_user_id() -> str:
        return "user-unverified"

    async def _fake_db_session():
        yield _UnverifiedSession()

    monkeypatch.setattr(SupabaseStorageClient, "upload", AsyncMock(return_value="https://example.com/x.jpg"))
    monkeypatch.setattr(GeminiVisionClient, "extract_menu_items", AsyncMock(return_value=[]))

    app.dependency_overrides[require_user_id] = _fake_user_id
    app.dependency_overrides[db_session] = _fake_db_session
    try:
        resp = client.post(
            "/v1/places/menu-reports/analyze",
            files={"image": ("photo.jpg", b"fake-bytes", "image/jpeg")},
        )
    finally:
        app.dependency_overrides.pop(require_user_id, None)
        app.dependency_overrides.pop(db_session, None)

    assert resp.status_code != 403
    assert resp.status_code == 200
    assert resp.json() == {"image_url": "https://example.com/x.jpg", "items": []}


# --- 보안 점검(vNext, 2026-08-31) — verify/report 엔드포인트가 UserDep(비로그인
# 통과, user_id="anonymous")에서 RequireUserDep(비로그인 401)으로 바뀐 것을
# 확인한다. 이 저장소의 다른 모든 쓰기 엔드포인트와 같은 순서 원칙: 401은 DB에
# 닿기 전에 나와야 한다(NullSession인 이 fixture로도 통과한다는 것 자체가 증거). ---


def test_create_verification_requires_login(client):
    resp = client.post("/v1/verifications", json={"report_id": 1, "verdict": "available"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_create_offer_verification_requires_login(client):
    resp = client.post("/v1/offers/1/verify", json={"verdict": "available"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_analyze_report_photo_requires_login(client):
    resp = client.post(
        "/v1/reports/analyze", files={"image": ("photo.jpg", b"fake-bytes", "image/jpeg")}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_submit_report_requires_login(client):
    resp = client.post("/v1/reports", json={"image_url": "https://example.com/x.jpg"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


# --- AI Price Discovery Engine 관리자 엔드포인트 — 다른 admin.py 엔드포인트와
# 동일하게 X-Admin-Key 없이는 DB에 닿기 전에 401로 막혀야 한다. ---


def test_price_discovery_run_rejects_without_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.post("/v1/admin/price-discovery/run")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_price_discovery_status_rejects_without_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.get("/v1/admin/price-discovery/status")
    assert resp.status_code == 401


def test_price_discovery_jobs_list_rejects_without_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.get("/v1/admin/price-discovery/jobs")
    assert resp.status_code == 401


def test_price_discovery_metrics_rejects_without_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.get("/v1/admin/price-discovery/metrics")
    assert resp.status_code == 401


def test_price_discovery_approve_rejects_without_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.post("/v1/admin/price-discovery/jobs/1/approve")
    assert resp.status_code == 401


def test_price_discovery_reject_rejects_without_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_sync_key", "real-secret")
    resp = client.post("/v1/admin/price-discovery/jobs/1/reject")
    assert resp.status_code == 401
