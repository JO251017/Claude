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


def test_ai_estimated_savings_with_no_behavior_signal_still_low_but_shows_the_number():
    # 행동 신호(방문/인증/추천)가 전혀 없으면 tier는 여전히 "low"이고 score/grade는
    # 지어내지 않지만(신뢰도는 실제 신호로만 매김), 계산 자체는 이미 됐다는 걸
    # "계산 중"으로 뭉개지 않고 정직하게 알려줘야 한다.
    r = _report(savings_rate=12.0, benchmark_source="ai")
    assert r.confidence_tier == "low"
    assert r.score is None
    assert r.grade is None
    assert "AI" in r.one_line
    assert any("AI" in reason for reason in r.reasons)


def test_region_estimated_savings_with_no_behavior_signal_mentions_region_not_ai():
    r = _report(savings_rate=12.0, benchmark_source="region")
    assert r.confidence_tier == "low"
    assert r.score is None
    assert "실측" in r.one_line
    assert "AI" not in r.one_line


def test_zero_savings_still_uses_generic_low_data_message():
    r = _report(savings_rate=0.0, benchmark_source="ai")
    assert r.one_line == "아직 충분한 데이터가 쌓이지 않아 절약 정보를 계산 중이에요."
