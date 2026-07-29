from app.core.spatial import haversine_m


def test_same_point_is_zero_distance():
    assert haversine_m(36.99, 127.11, 36.99, 127.11) == 0.0


def test_known_distance_approx():
    # 평택시청 근처 두 좌표, 대략 300m 정도 떨어진 값으로 어림 검증
    d = haversine_m(36.9925, 127.1130, 36.9950, 127.1130)
    assert 250 < d < 350
