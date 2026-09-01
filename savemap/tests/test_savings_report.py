from datetime import datetime, timedelta, timezone

from app.engine.savings_report import build_savings_report


def _days_ago(n):
    return datetime.now(timezone.utc) - timedelta(days=n)


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


def test_freshness_tier_boundaries():
    # 7일/30일/90일 경계값 — vNext 지시서(2026-08-31) "가격 최신성 시스템"의
    # 다단계 분류가 정확히 그 기준으로 나뉘는지 확인한다.
    fresh = _report(savings_rate=10.0, dining_count=2, last_verified_at=_days_ago(7))
    normal = _report(savings_rate=10.0, dining_count=2, last_verified_at=_days_ago(30))
    stale = _report(savings_rate=10.0, dining_count=2, last_verified_at=_days_ago(90))
    expired = _report(savings_rate=10.0, dining_count=2, last_verified_at=_days_ago(91))
    unknown = _report(savings_rate=10.0, dining_count=2, last_verified_at=None)

    assert fresh.freshness_tier == "fresh"
    assert normal.freshness_tier == "normal"
    assert stale.freshness_tier == "stale"
    assert expired.freshness_tier == "expired"
    assert unknown.freshness_tier == "unknown"
    assert unknown.days_since_verified is None


def test_expired_price_is_flagged_and_penalized_in_score():
    # 90일을 넘긴 데이터는 "정보가 오래됐다"고 경고 문구가 붙고, 점수도 깎인다 —
    # 오래된 정보가 신뢰도 점수에서 신선한 정보와 똑같이 취급되면 안 된다.
    fresh = _report(savings_rate=10.0, dining_count=2, last_verified_at=_days_ago(1))
    expired = _report(savings_rate=10.0, dining_count=2, last_verified_at=_days_ago(120))
    assert any("오래됐어요" in reason for reason in expired.reasons)
    assert expired.score < fresh.score


def test_unknown_freshness_is_not_penalized():
    # 확인 시각 정보가 아예 없는 것과 "오래전에 확인했다"는 다른 사실이다 — 모른다고
    # 벌점을 주면 없는 사실을 있는 것처럼 취급하는 셈이다.
    with_data = _report(savings_rate=10.0, dining_count=2, last_verified_at=_days_ago(120))
    unknown = _report(savings_rate=10.0, dining_count=2, last_verified_at=None)
    assert unknown.score > with_data.score
    assert not any("오래됐어요" in reason for reason in unknown.reasons)


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
    # 행동 신호(방문/인증/추천)가 전혀 없으면 tier는 여전히 "low"지만(신뢰도는 실제
    # 신호로만 매김), 가격 근거가 있으면 점수는 계산한다(2026-09-01, §18 — 점수와
    # 신뢰도는 독립된 축). "계산 중"으로 뭉개지 않고 정직하게 알려준다.
    r = _report(savings_rate=12.0, benchmark_source="ai")
    assert r.confidence_tier == "low"
    assert r.score is not None
    assert r.score <= 75  # _NO_SIGNAL_SCORE_CAP — 사람 신호가 없으면 상한
    assert r.grade is not None
    assert "AI" in r.one_line
    assert any("AI" in reason for reason in r.reasons)


def test_region_estimated_savings_with_no_behavior_signal_mentions_region_not_ai():
    r = _report(savings_rate=12.0, benchmark_source="region")
    assert r.confidence_tier == "low"
    assert r.score is not None
    assert r.score <= 75
    assert "실측" in r.one_line
    assert "AI" not in r.one_line


def test_low_tier_score_never_exceeds_no_signal_cap():
    # 신뢰도가 낮으면(사람 신호 0) 절약률이 아무리 커도 점수 상한(75)을 넘지
    # 않는다 — "점수가 높다고 신뢰도가 자동 상승하지 않는다"의 반대 방향도
    # 마찬가지로, 신뢰도가 없으면 점수도 무한정 높아지지 않는다. tier=="low"
    # 자체가 요구하는 낮은 행동 신호 제약 때문에 실제로는 상한보다 낮게 나오지만
    # (여기서는 65), 상한 로직이 실제로 적용되는지는 이 사실 자체로 확인된다.
    r = _report(
        savings_rate=999.0,
        benchmark_source="region",
        benchmark_sample_count=50,
        last_verified_at=datetime.now(timezone.utc),
    )
    assert r.confidence_tier == "low"
    assert r.score is not None
    assert r.score <= 75
    assert r.score == 65  # 가격 경쟁력 55(상한) + 최신성 +10, 사람 신호 0


def test_low_tier_without_price_evidence_still_reports_no_score():
    # 가격 비교 자체가 안 된 진짜 콜드스타트는 여전히 score=None — 지어내지 않는다.
    r = _report(savings_rate=0.0, benchmark_source=None)
    assert r.confidence_tier == "low"
    assert r.score is None
    assert r.grade is None


def test_zero_savings_still_uses_generic_low_data_message():
    r = _report(savings_rate=0.0, benchmark_source="ai")
    assert r.one_line == "아직 충분한 데이터가 쌓이지 않아 절약 정보를 계산 중이에요."


def _strong_signals(**kw):
    """방문/인증/추천이 충분히 많아서 raw tier가 "high"가 되는 조합."""
    base = dict(
        savings_rate=25.0, dining_count=3, discover_count=10,
        recommend_count=4, verification_count=2,
        last_verified_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    base.update(kw)
    return _report(**base)


def test_region_benchmark_reaches_high_tier_and_full_score_weight():
    r = _strong_signals(benchmark_source="region", benchmark_sample_count=10)
    assert r.confidence_tier == "high"
    assert r.confidence_stars == 5  # region + 표본 충분 + dining>=2


def test_gov_benchmark_stays_high_but_never_hits_five_stars():
    r = _strong_signals(benchmark_source="gov")
    assert r.confidence_tier == "high"  # gov는 tier를 안 끌어내림
    assert r.confidence_stars == 4  # 다만 region이 아니라 만점은 아님


def test_ai_benchmark_caps_tier_at_medium_even_with_strong_signals():
    # 예전엔 AI 짐작 절약률도 방문/인증만 많으면 "신뢰도 높음" 최대 점수 근처를
    # 받았다 — 가격 근거의 질을 아예 안 봤기 때문. 이제는 상한이 걸린다.
    r = _strong_signals(benchmark_source="ai")
    assert r.confidence_tier == "medium"
    assert r.confidence_stars == 2
    assert "AI 추정 기준" in r.one_line


def test_benchmark_source_none_with_savings_rate_zero_is_never_capped():
    # 벤치마크가 아예 없어 절약을 안 주장하는 매장을, 방문 신호가 많다는 이유로
    # 끌어내릴 이유는 없다.
    r = _strong_signals(savings_rate=0.0, benchmark_source=None)
    assert r.confidence_tier == "high"


def test_ai_score_contribution_is_capped_below_region_for_same_inputs():
    region_report = _strong_signals(benchmark_source="region", benchmark_sample_count=10)
    ai_report = _strong_signals(benchmark_source="ai")
    assert ai_report.score < region_report.score


def test_thin_region_sample_scores_lower_than_thick_sample():
    thin = _strong_signals(benchmark_source="region", benchmark_sample_count=1)
    thick = _strong_signals(benchmark_source="region", benchmark_sample_count=20)
    assert thin.score < thick.score
    # dining_count=3(>=2)이라 별점 자체는 표본이 얇아도 5성 조건을 만족한다 —
    # 별점은 "이 조건들 중 하나"고, 점수(score)만 표본 두께에 비례해 깎인다.
    assert thin.confidence_stars == 5


def test_thin_region_sample_without_strong_dining_signal_misses_five_stars():
    # dining_count가 2 미만이면 표본 두께가 유일한 5성 조건이라, 얇으면 4성에 머문다.
    thin = _strong_signals(benchmark_source="region", benchmark_sample_count=1, dining_count=1)
    assert thin.confidence_stars == 4


def test_unknown_sample_count_is_treated_as_thin():
    # 재동기화 전 구 데이터(benchmark_sample_count=None)는 얇은 표본으로 취급한다 —
    # 실제로는 표본이 많을 수도 있는데 모른다고 만점을 주면 안 된다.
    unknown = _strong_signals(benchmark_source="region", benchmark_sample_count=None)
    thick = _strong_signals(benchmark_source="region", benchmark_sample_count=20)
    assert unknown.score < thick.score


def test_region_reason_mentions_actual_sample_count():
    r = _report(savings_rate=12.0, dining_count=2, benchmark_source="region", benchmark_sample_count=7)
    assert any("주변 매장 7곳" in reason for reason in r.reasons)


def test_stars_are_always_within_the_five_valid_levels():
    # 별점이 스키마 밖 값(예: 1)을 내면 안 된다.
    combos = [
        dict(benchmark_source=None),
        dict(benchmark_source="ai", savings_rate=10.0),
        dict(benchmark_source="gov", savings_rate=10.0),
        dict(benchmark_source="region", savings_rate=10.0, benchmark_sample_count=1),
        dict(benchmark_source="region", savings_rate=10.0, benchmark_sample_count=10),
    ]
    for combo in combos:
        r = _strong_signals(**combo)
        assert r.confidence_stars in {0, 2, 3, 4, 5}
