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


def test_admin_endpoints_disabled_when_key_not_configured(client, monkeypatch):
    from app.core.config import settings

    # 운영에서 ADMIN_SYNC_KEY를 아예 안 넣으면(빈 문자열) 어떤 키를 보내도 거부돼야
    # 한다 — "설정 안 하면 관리자 API 자체가 잠긴다"는 안전장치가 실제로 동작하는지.
    monkeypatch.setattr(settings, "admin_sync_key", "")
    resp = client.get("/v1/admin/places/stats", headers={"X-Admin-Key": ""})
    assert resp.status_code == 401


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
