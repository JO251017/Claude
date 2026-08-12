from app.core.rate_limit import ADMIN_LIMIT


def test_health_endpoint_is_never_rate_limited(client):
    # 헬스체크(Render 자체 + keep-alive 핑)는 자주 불릴 수밖에 없으니 제한 대상이 아니다.
    for _ in range(ADMIN_LIMIT + 10):
        resp = client.get("/health", headers={"X-Forwarded-For": "9.9.9.9"})
        assert resp.status_code == 200


def test_admin_endpoint_blocks_after_limit_from_same_ip(client):
    ip = "1.2.3.4"
    # 한도까지는(인증 실패라 401이지만) 레이트리밋에는 안 걸려야 한다.
    for _ in range(ADMIN_LIMIT):
        resp = client.get("/v1/admin/places/stats", headers={"X-Forwarded-For": ip})
        assert resp.status_code != 429

    # 한도를 넘긴 다음 요청은 429여야 한다.
    resp = client.get("/v1/admin/places/stats", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 429
    body = resp.json()
    assert body["code"] == "SM4291"
    assert resp.headers.get("retry-after") is not None


def test_different_ips_have_independent_limits(client):
    ip_a = "10.0.0.1"
    ip_b = "10.0.0.2"
    for _ in range(ADMIN_LIMIT):
        client.get("/v1/admin/places/stats", headers={"X-Forwarded-For": ip_a})
    # A는 한도를 다 썼지만, B는 별개 버킷이라 여전히 통과해야 한다.
    resp = client.get("/v1/admin/places/stats", headers={"X-Forwarded-For": ip_b})
    assert resp.status_code != 429


def test_x_forwarded_for_uses_leftmost_ip(client):
    # 프록시 체인을 여러 개 거쳐도(가장 왼쪽 = 최초 클라이언트) 같은 사용자로 인식돼야
    # 카운트가 제대로 누적된다.
    header = "203.0.113.5, 70.41.3.18, 150.172.238.178"
    for _ in range(ADMIN_LIMIT):
        client.get("/v1/admin/places/stats", headers={"X-Forwarded-For": header})
    resp = client.get("/v1/admin/places/stats", headers={"X-Forwarded-For": header})
    assert resp.status_code == 429
