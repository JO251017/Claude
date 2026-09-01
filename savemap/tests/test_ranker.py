from datetime import datetime, timedelta, timezone

from app.domain.enums import Category, Layer, SourceType
from app.engine.models import OfferCandidate
from app.engine.ranker import (
    _distance_norm,
    _freshness_multiplier,
    _source_quality_multiplier,
    _weather_norm,
    dedupe_by_place,
    rank_candidates,
)
from app.integrations.weather import WeatherSnapshot


def _c(offer_id: int, base: float, discount: float, trust: float) -> OfferCandidate:
    return OfferCandidate(
        offer_id=offer_id,
        place_id=offer_id,
        place_name=f"p{offer_id}",
        category=Category.DISCOUNT,
        layer=Layer.REGULAR,
        distance_m=100.0,
        base_price=base,
        lat=36.99,
        lng=127.11,
        store_discount=discount,
        trust_score=trust,
    )


def test_ranks_by_savings_and_trust():
    high_savings_low_trust = _c(1, 10000, 5000, 0.1)
    low_savings_high_trust = _c(2, 10000, 1000, 0.9)
    ranked = rank_candidates([low_savings_high_trust, high_savings_low_trust])
    assert ranked[0].candidate.offer_id == 1
    assert ranked[0].score >= ranked[1].score


def _at_place(offer_id: int, place_id: int, discount: float) -> OfferCandidate:
    c = _c(offer_id, 10000, discount, 0.5)
    c.place_id = place_id
    return c


def test_dedupe_by_place_keeps_only_top_scored_offer_per_place():
    # 매장 3(place_id=3)에 오퍼가 2개(하나는 할인 큼, 하나는 작음) — 점수 높은 것만 남아야 함.
    candidates = [
        _at_place(1, place_id=3, discount=1000),  # 낮은 절약
        _at_place(2, place_id=3, discount=9000),  # 높은 절약 — 이게 대표로 남아야 함
        _at_place(3, place_id=5, discount=500),
    ]
    ranked = rank_candidates(candidates)
    deduped = dedupe_by_place(ranked)

    place_ids = [r.candidate.place_id for r in deduped]
    assert sorted(place_ids) == [3, 5]
    winning = next(r for r in deduped if r.candidate.place_id == 3)
    assert winning.candidate.offer_id == 2  # 절약 큰 쪽이 대표로 남음


def test_dedupe_by_place_caps_at_max_results():
    candidates = [_at_place(i, place_id=i, discount=1000) for i in range(10)]
    ranked = rank_candidates(candidates)
    deduped = dedupe_by_place(ranked, max_results=3)
    assert len(deduped) == 3
    # 정렬 순서(점수 내림차순) 그대로 상위 3개가 남아야 한다
    assert [r.score for r in deduped] == sorted([r.score for r in ranked], reverse=True)[:3]


def test_dedupe_by_place_no_cap_when_max_results_none():
    candidates = [_at_place(i, place_id=i, discount=1000) for i in range(5)]
    ranked = rank_candidates(candidates)
    assert len(dedupe_by_place(ranked)) == 5


# --- 랭킹에 거리 반영(2026-08-22) — 거리가 전혀 안 들어가서, 검증 데이터가 적은
# 콜드스타트에선 거의 모든 후보가 동점(0.15)이 돼 정렬이 "우연히" 거리순으로만
# 남는 상태였다. 쌍곡 감쇠 + 명시적 타이브레이크로 의도된 동작으로 바꿨다. ---


def test_distance_norm_is_one_at_zero_distance():
    assert _distance_norm(0.0) == 1.0


def test_distance_norm_is_half_at_the_half_distance(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "rank_distance_half_m", 500.0)
    assert _distance_norm(500.0) == 0.5


def test_distance_norm_decreases_monotonically():
    values = [_distance_norm(d) for d in (0, 250, 500, 1000, 3000, 10000)]
    assert values == sorted(values, reverse=True)
    assert all(v > 0 for v in values)  # 지수 감쇠와 달리 반경 끝에서 0으로 안 죽는다


def test_closer_candidate_wins_when_savings_and_trust_are_equal():
    far = _c(1, 10000, 2000, 0.5)
    far.distance_m = 2000.0
    near = _c(2, 10000, 2000, 0.5)
    near.distance_m = 100.0
    ranked = rank_candidates([far, near])
    assert ranked[0].candidate.offer_id == 2


def test_completely_tied_candidates_break_ties_by_distance_then_offer_id():
    # 콜드스타트에서 흔한 상태: 절약률 0, trust 기본값(0.5) 동일 → 점수도 동일.
    # 입력 순서를 뒤집어도 결과가 항상 같아야(=결정론적) 한다.
    a = _c(offer_id=5, base=10000, discount=0, trust=0.5)
    a.distance_m = 300.0
    b = _c(offer_id=3, base=10000, discount=0, trust=0.5)
    b.distance_m = 300.0

    forward = rank_candidates([a, b])
    backward = rank_candidates([b, a])
    assert [r.candidate.offer_id for r in forward] == [3, 5]
    assert [r.candidate.offer_id for r in backward] == [3, 5]


# --- 날씨 기반 추천(2026-08-27) — 날씨 데이터가 없으면 기존 순위가 완전히
# 그대로여야 하고, 있을 때만 실제로 맞는 업종에만 살짝 가중치가 붙어야 한다. ---


def test_weather_norm_is_neutral_without_weather_data():
    assert _weather_norm("음식점 > 카페 > 커피전문점", None) == 0.5


def test_weather_norm_is_neutral_when_category_unclassifiable():
    rain = WeatherSnapshot("rain", 20.0, datetime.now(timezone.utc))
    assert _weather_norm(None, rain) == 0.5
    assert _weather_norm("휴게음식점", rain) == 0.5  # activity_classifier가 못 알아내는 업종


def test_weather_norm_boosts_cafe_on_rain_but_not_dining():
    rain = WeatherSnapshot("rain", 20.0, datetime.now(timezone.utc))
    assert _weather_norm("음식점 > 카페 > 커피전문점", rain) > 0.5
    assert _weather_norm("일반음식점 > 한식", rain) == 0.5


def test_weather_norm_boosts_cafe_and_dessert_on_heat():
    hot = WeatherSnapshot("clear", 31.0, datetime.now(timezone.utc), is_hot=True)
    assert _weather_norm("카페", hot) > 0.5
    assert _weather_norm("휴게음식점 > 제과점영업", hot) > 0.5  # 디저트류
    assert _weather_norm("일반음식점 > 한식", hot) == 0.5


def test_weather_norm_boosts_dining_on_cold():
    cold = WeatherSnapshot("clear", -1.0, datetime.now(timezone.utc), is_cold=True)
    assert _weather_norm("일반음식점 > 국밥", cold) > 0.5
    assert _weather_norm("카페", cold) == 0.5


def test_rank_candidates_without_weather_matches_default_ranking():
    """weather 인자를 안 넘기면(기존 호출부 route.py 등) 결과가 예전과 완전히
    동일해야 한다 — 하위호환 보장."""
    cafe = _c(1, 10000, 2000, 0.5)
    cafe.place_category_name = "카페"
    dining = _c(2, 10000, 2000, 0.5)
    dining.place_category_name = "일반음식점 > 한식"

    without_arg = rank_candidates([cafe, dining])
    with_none = rank_candidates([cafe, dining], weather=None)
    assert [r.score for r in without_arg] == [r.score for r in with_none]


def test_rank_candidates_with_rain_favors_cafe_when_otherwise_tied():
    cafe = _c(1, 10000, 2000, 0.5)
    cafe.place_category_name = "카페"
    dining = _c(2, 10000, 2000, 0.5)
    dining.place_category_name = "일반음식점 > 한식"

    rain = WeatherSnapshot("rain", 20.0, datetime.now(timezone.utc))
    ranked = rank_candidates([dining, cafe], weather=rain)
    assert ranked[0].candidate.offer_id == 1  # 카페가 비 오는 날 위로 옴


# --- 가격 최신성 랭킹 반영(vNext, 2026-08-31) — 90일 넘게 확인 안 된 후보는
# 신뢰도 항목이 살짝 깎여야 하고, 확인 시각 정보가 아예 없는 경우(unknown)는
# "오래됐다"고 단정하지 않으므로 깎이면 안 된다. ---


def test_freshness_multiplier_penalizes_only_expired():
    now = datetime.now(timezone.utc)
    assert _freshness_multiplier(None) == 1.0  # 확인 시각 정보 없음(unknown) — 안 깎음
    assert _freshness_multiplier(now - timedelta(days=1)) == 1.0  # fresh
    assert _freshness_multiplier(now - timedelta(days=90)) == 1.0  # stale(경계 이내)
    assert _freshness_multiplier(now - timedelta(days=91)) < 1.0  # expired


def test_expired_freshness_lowers_rank_when_otherwise_tied():
    fresh = _c(1, 10000, 2000, 0.8)
    fresh.last_verified_at = datetime.now(timezone.utc) - timedelta(days=1)
    expired = _c(2, 10000, 2000, 0.8)
    expired.last_verified_at = datetime.now(timezone.utc) - timedelta(days=200)

    ranked = rank_candidates([expired, fresh])
    assert ranked[0].candidate.offer_id == 1  # 최신 정보 쪽이 위로 옴
    assert ranked[0].score > ranked[1].score


def test_unknown_freshness_is_not_penalized_in_ranking():
    # last_verified_at이 아예 없는 후보는 penalty가 없어야 한다 — trust_score만
    # 같으면 순위도 같아야(=동점) 한다.
    unknown = _c(1, 10000, 2000, 0.8)
    fresh = _c(2, 10000, 2000, 0.8)
    fresh.last_verified_at = datetime.now(timezone.utc) - timedelta(days=1)

    ranked = rank_candidates([unknown, fresh])
    assert ranked[0].score == ranked[1].score


# --- 데이터 품질(2026-09-01, §24~25) ---


def test_source_quality_multiplier_unknown_source_not_penalized():
    # source가 아예 없으면(구 데이터) 벌점을 주지 않는다 — freshness와 같은 원칙.
    assert _source_quality_multiplier(None) == 1.0


def test_source_quality_multiplier_ranks_verification_highest():
    assert _source_quality_multiplier(SourceType.S5_VERIFICATION) == 1.0
    assert _source_quality_multiplier(SourceType.S6_AI_DISCOVERY_WEB) < _source_quality_multiplier(
        SourceType.S5_VERIFICATION
    )


def test_low_quality_source_lowers_rank_when_otherwise_tied():
    verified = _c(1, 10000, 2000, 0.8)
    verified.source = SourceType.S5_VERIFICATION
    ai_web = _c(2, 10000, 2000, 0.8)
    ai_web.source = SourceType.S6_AI_DISCOVERY_WEB

    ranked = rank_candidates([ai_web, verified])
    assert ranked[0].candidate.offer_id == 1  # 사용자 인증 출처가 위로 옴
    assert ranked[0].score > ranked[1].score


def test_unknown_source_is_not_penalized_in_ranking():
    unknown = _c(1, 10000, 2000, 0.8)
    verified = _c(2, 10000, 2000, 0.8)
    verified.source = SourceType.S5_VERIFICATION

    ranked = rank_candidates([unknown, verified])
    assert ranked[0].score == ranked[1].score
