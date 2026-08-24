"""검색과 AI 절약 플랜이 공유하는 정렬 키(app/engine/ordering.py). route_planner의
_preference_sort_key가 원래 있던 로직을 그대로 옮긴 것이라, 이 파일의 테스트는
사실상 route_planner의 정렬 동작을 여기서도 고정해두는 역할이다."""
import pytest

from app.engine.ordering import sort_key_for


def test_cheapest_sorts_by_final_price():
    class _R:
        def __init__(self, price):
            self.breakdown = type("B", (), {"final_price": price})()

    items = [_R(3000), _R(1000), _R(2000)]
    ordered = sorted(items, key=sort_key_for("cheapest"))
    assert [r.breakdown.final_price for r in ordered] == [1000, 2000, 3000]


def test_verified_prefers_higher_trust_then_more_verifications():
    class _R:
        def __init__(self, trust, count):
            self.candidate = type(
                "C", (), {"trust_score": trust, "verification_count": count}
            )()

    a = _R(0.9, 1)
    b = _R(0.9, 5)
    c = _R(0.3, 100)
    ordered = sorted([c, a, b], key=sort_key_for("verified"))
    assert ordered == [b, a, c]  # trust 동률이면 검증 횟수 많은 쪽이 앞


def test_recent_prefers_later_timestamp_and_none_goes_last():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    class _R:
        def __init__(self, ts):
            self.candidate = type("C", (), {"last_verified_at": ts})()

    newer = _R(now)
    older = _R(now - timedelta(days=10))
    unknown = _R(None)
    ordered = sorted([unknown, older, newer], key=sort_key_for("recent"))
    assert ordered == [newer, older, unknown]


def test_distance_prefers_closer():
    class _R:
        def __init__(self, d):
            self.candidate = type("C", (), {"distance_m": d})()

    far = _R(3000.0)
    near = _R(100.0)
    ordered = sorted([far, near], key=sort_key_for("distance"))
    assert ordered == [near, far]


def test_unknown_sort_name_raises():
    with pytest.raises(ValueError):
        sort_key_for("nonsense")
