from datetime import datetime, timedelta, timezone

from app.engine.freshness import freshness_tier


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
