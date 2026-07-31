from datetime import datetime, timedelta, timezone

from app.engine.savings_report import build_savings_report


def _report(**kw):
    base = dict(
        savings_rate=0.0,
        discover_count=0,
        dining_count=0,
        recommend_count=0,
        verification_count=0,
        last_verified_at=None,
        benchmark_source=None,
    )
    base.update(kw)
    return build_savings_report(**base)


def test_no_data_reports_low_confidence_without_a_fabricated_score():
    r = _report()
    assert r.confidence_tier == "low"
    assert r.score is None
    assert r.grade is None
    assert "부족" in "".join(r.reasons)


def test_strong_real_signals_produce_high_confidence_and_grade():
    r = _report(
        savings_rate=25.0,
        dining_count=3,
        discover_count=10,
        recommend_count=4,
        verification_count=2,
        last_verified_at=datetime.now(timezone.utc) - timedelta(days=1),
        benchmark_source="region",
    )
    assert r.confidence_tier == "high"
    assert r.score is not None and r.score > 60
    assert r.grade in {"S+", "S", "A+", "A"}
    assert any("영수증 인증 3건" in reason for reason in r.reasons)


def test_stale_verification_does_not_count_as_fresh():
    r = _report(
        savings_rate=10.0,
        dining_count=2,
        last_verified_at=datetime.now(timezone.utc) - timedelta(days=90),
    )
    assert not any("이내 데이터 반영" in reason for reason in r.reasons)


def test_score_never_exceeds_100():
    r = _report(
        savings_rate=999.0,
        dining_count=999,
        discover_count=999,
        recommend_count=999,
        last_verified_at=datetime.now(timezone.utc),
    )
    assert r.score == 100
    assert r.grade == "S+"


def test_medium_confidence_without_enough_for_high():
    r = _report(savings_rate=5.0, discover_count=3)
    assert r.confidence_tier == "medium"
    assert r.score is not None
