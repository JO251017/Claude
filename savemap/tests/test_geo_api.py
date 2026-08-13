"""GET /geo/search (주소 순방향 검색, 1번 항목) 라우트 레벨 테스트.

KakaoClient.geocode()는 이미 있었지만 HTTP로 노출된 적이 없었다 — 새 라우트가
성공/실패(못 찾음/카카오 API 예외) 케이스를 올바른 모양으로 응답하는지만 확인한다.
"""

from unittest.mock import AsyncMock, patch

from app.integrations.kakao import GeocodeResult


def test_search_address_success_returns_lat_lng_address(client):
    fake_result = GeocodeResult(lat=37.5665, lng=126.9780, address="서울 중구 세종대로 110")
    with patch(
        "app.integrations.kakao.KakaoClient.geocode", new=AsyncMock(return_value=fake_result)
    ):
        resp = client.get("/v1/geo/search", params={"query": "서울시청"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["lat"] == 37.5665
    assert body["lng"] == 126.978
    assert body["address"] == "서울 중구 세종대로 110"


def test_search_address_not_found_returns_found_false(client):
    with patch("app.integrations.kakao.KakaoClient.geocode", new=AsyncMock(return_value=None)):
        resp = client.get("/v1/geo/search", params={"query": "존재하지않는주소이상한값"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is False
    assert body["lat"] is None
    assert body["address"] is None


def test_search_address_kakao_exception_returns_found_false_not_500(client):
    with patch(
        "app.integrations.kakao.KakaoClient.geocode", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        resp = client.get("/v1/geo/search", params={"query": "아무거나"})
    assert resp.status_code == 200
    assert resp.json()["found"] is False


def test_search_address_requires_nonempty_query(client):
    resp = client.get("/v1/geo/search", params={"query": ""})
    assert resp.status_code == 422
