"""CORS는 app 생성 시점(create_app())에 설정값을 읽어 미들웨어 스택을 짜므로,
공용 client 픽스처(이미 만들어진 app 싱글턴을 감싸는)로는 설정을 바꿔가며 테스트할
수 없다 — 여기선 create_app()을 직접 다시 호출해서 그때그때 다른 설정으로
검증한다."""

from starlette.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def test_no_cors_headers_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "cors_allowed_origins", "")
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers


def test_cors_headers_present_for_allowed_origin(monkeypatch):
    monkeypatch.setattr(settings, "cors_allowed_origins", "https://app.example.com,https://m.example.com")
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": "https://app.example.com"})
    assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_cors_rejects_origin_not_in_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "cors_allowed_origins", "https://app.example.com")
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers


def test_cors_preflight_allows_configured_origin(monkeypatch):
    monkeypatch.setattr(settings, "cors_allowed_origins", "https://app.example.com")
    app = create_app()
    with TestClient(app) as client:
        resp = client.options(
            "/v1/search",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"
