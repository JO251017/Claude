from datetime import datetime, timedelta, timezone

from app.engine.freshness import freshness_breakdown, freshness_tier


def _ago(days):
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_none_is_unknown_not_expired():
    tier, days = freshness_tier(None)
    assert tier == "unknown"
    assert days is None


def test_boundaries_are_inclusive():
    now = datetime.now(timezone.utc)
    assert freshness_tier(now - timedelta(days=7), now=now) == ("fresh", 7)
    assert freshness_tier(now - timedelta(days=8), now=now) == ("normal", 8)
    assert freshness_tier(now - timedelta(days=30), now=now) == ("normal", 30)
    assert freshness_tier(now - timedelta(days=31), now=now) == ("stale", 31)
    assert freshness_tier(now - timedelta(days=90), now=now) == ("stale", 90)
    assert freshness_tier(now - timedelta(days=91), now=now) == ("expired", 91)


def test_zero_days_is_fresh():
    now = datetime.now(timezone.utc)
    assert freshness_tier(now, now=now) == ("fresh", 0)


# --- freshness_breakdown: GET /admin/places/stats의 검증 요약이 쓰는 집계 함수
# (2026-08-31, 오퍼 재동기화 배치가 실제로 이력을 남겼는지 확인할 방법이 없어서
# 추가됨) ---


def test_breakdown_counts_each_tier():
    now = datetime.now(timezone.utc)
    observed_ats = [now, now - timedelta(days=8), now - timedelta(days=91), None]
    result = freshness_breakdown(observed_ats, now=now)
    assert result == {"fresh": 1, "normal": 1, "expired": 1, "unknown": 1}


def test_breakdown_empty_input_is_empty_dict():
    assert freshness_breakdown([]) == {}
