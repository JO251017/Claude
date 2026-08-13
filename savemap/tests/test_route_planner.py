import asyncio
from datetime import datetime, timedelta, timezone

from app.domain.enums import Category, Layer, RoutePreference
from app.engine.models import OfferCandidate
from app.engine.ranker import rank_candidates
from app.engine.route_planner import _fallback_summary, build_route, generate_summary


def _c(
    offer_id: int,
    category: Category,
    base: float,
    discount: float = 0.0,
    distance_m: float = 100.0,
    trust_score: float = 0.5,
    verification_count: int = 0,
    last_verified_at=None,
) -> OfferCandidate:
    return OfferCandidate(
        offer_id=offer_id,
        place_id=offer_id,
        place_name=f"place{offer_id}",
        category=category,
        layer=Layer.REGULAR,
        distance_m=distance_m,
        base_price=base,
        lat=36.99,
        lng=127.11,
        store_discount=discount,
        trust_score=trust_score,
        verification_count=verification_count,
        last_verified_at=last_verified_at,
    )


def test_build_route_picks_diverse_categories_within_budget():
    candidates = [
        _c(1, Category.FREE_PARKING, base=0),
        _c(2, Category.FREE, base=0),
        _c(3, Category.DISCOUNT, base=12000, discount=2000),  # final 10,000
        _c(4, Category.CLOSING_SOON, base=28000, discount=0),  # final 28,000
    ]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=40000, max_stops=4)

    assert plan.fits_budget is True
    categories = {s.ranked.candidate.category for s in plan.stops}
    assert categories == {Category.FREE_PARKING, Category.FREE, Category.DISCOUNT, Category.CLOSING_SOON}
    assert plan.total_spend == 38000
    assert plan.remaining_budget == 2000


def test_build_route_fill_pass_uses_remaining_budget_when_categories_run_out():
    # 카테고리가 2종류뿐이라도, 예산/슬롯이 남으면 2차 패스가 나머지를 채운다.
    candidates = [
        _c(1, Category.DISCOUNT, base=3000),
        _c(2, Category.DISCOUNT, base=3000),
        _c(3, Category.FREE, base=0),
    ]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=10000, max_stops=4)

    assert len(plan.stops) == 3  # 후보가 3개뿐이라 그 이상은 못 채움
    assert plan.fits_budget is True


def test_build_route_respects_max_stops():
    candidates = [_c(i, Category.DISCOUNT, base=1000) for i in range(10)]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=100000, max_stops=3)
    assert len(plan.stops) == 3


def test_build_route_returns_empty_plan_when_nothing_fits_budget():
    candidates = [_c(1, Category.DISCOUNT, base=50000)]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=1000, max_stops=4)

    assert plan.stops == []
    assert plan.fits_budget is False
    assert plan.total_spend == 0
    assert plan.remaining_budget == 1000


def test_build_route_orders_free_stops_before_paid_ascending_by_price():
    candidates = [
        _c(1, Category.DISCOUNT, base=28000),  # 비쌈, 무료 아님
        _c(2, Category.FREE, base=0),
        _c(3, Category.CLOSING_SOON, base=12000),
    ]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=50000, max_stops=3)

    prices = [s.ranked.breakdown.final_price for s in plan.stops]
    assert prices == sorted(prices)
    assert plan.stops[0].ranked.candidate.category == Category.FREE
    assert [s.order for s in plan.stops] == [1, 2, 3]


def test_fallback_summary_never_fabricates_numbers():
    candidates = [_c(1, Category.FREE, base=0), _c(2, Category.DISCOUNT, base=8000)]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=20000, max_stops=4)

    text = _fallback_summary(plan.stops, plan.total_spend, plan.total_savings)
    for stop in plan.stops:
        assert stop.ranked.candidate.place_name in text
    assert f"{plan.total_spend:,.0f}" in text


def test_fallback_summary_handles_empty_stops():
    text = _fallback_summary([], 0.0, 0.0)
    assert "코스" in text or "조건" in text


def test_generate_summary_skips_gemini_and_uses_template_when_no_stops():
    plan = build_route([], budget=10000, max_stops=4)
    text, source = asyncio.run(generate_summary(plan, party_size=2))
    assert source == "template"
    assert plan.stops == []


def test_generate_summary_uses_ai_when_gemini_returns_text():
    class _FakeGemini:
        async def summarize_route(self, **kwargs):
            return "AI가 쓴 문장"

    candidates = [_c(1, Category.FREE, base=0)]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=5000, max_stops=4)

    text, source = asyncio.run(generate_summary(plan, party_size=1, gemini=_FakeGemini()))
    assert text == "AI가 쓴 문장"
    assert source == "ai"


def test_generate_summary_falls_back_to_template_when_gemini_returns_none():
    class _FailingGemini:
        async def summarize_route(self, **kwargs):
            return None

    candidates = [_c(1, Category.FREE, base=0)]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=5000, max_stops=4)

    text, source = asyncio.run(generate_summary(plan, party_size=1, gemini=_FailingGemini()))
    assert source == "template"
    assert plan.stops[0].ranked.candidate.place_name in text


def test_generate_summary_forwards_context_note_to_gemini():
    captured = {}

    class _FakeGemini:
        async def summarize_route(self, **kwargs):
            captured.update(kwargs)
            return "문장"

    candidates = [_c(1, Category.FREE, base=0)]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=5000, max_stops=4)

    asyncio.run(
        generate_summary(
            plan, party_size=1, gemini=_FakeGemini(), context_note="활동: 식사"
        )
    )
    assert captured["context_note"] == "활동: 식사"


# --- preference: build_route가 선택 순서를 실제로 바꾸는지(사용자 지시, 2026-08-13) ---


def test_no_preference_keeps_existing_rank_score_order():
    # preference를 안 넘기면 기존 동작(rank_candidates가 이미 매긴 점수순) 그대로다.
    candidates = [_c(1, Category.DISCOUNT, base=1000), _c(2, Category.DISCOUNT, base=1000)]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=1000, max_stops=1, preference=None)
    assert len(plan.stops) == 1
    assert plan.stops[0].ranked.candidate.offer_id == ranked[0].candidate.offer_id


def test_cheapest_preference_picks_lowest_price_first():
    candidates = [
        _c(1, Category.DISCOUNT, base=9000),
        _c(2, Category.DISCOUNT, base=1000),
        _c(3, Category.DISCOUNT, base=5000),
    ]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=1000, max_stops=1, preference=RoutePreference.CHEAPEST)
    assert len(plan.stops) == 1
    assert plan.stops[0].ranked.candidate.offer_id == 2


def test_verified_preference_prefers_higher_trust_score():
    candidates = [
        _c(1, Category.DISCOUNT, base=1000, trust_score=0.3),
        _c(2, Category.DISCOUNT, base=1000, trust_score=0.9),
    ]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=1000, max_stops=1, preference=RoutePreference.VERIFIED)
    assert plan.stops[0].ranked.candidate.offer_id == 2


def test_recent_preference_prefers_most_recently_verified():
    now = datetime.now(timezone.utc)
    candidates = [
        _c(1, Category.DISCOUNT, base=1000, last_verified_at=now - timedelta(days=30)),
        _c(2, Category.DISCOUNT, base=1000, last_verified_at=now - timedelta(days=1)),
        _c(3, Category.DISCOUNT, base=1000, last_verified_at=None),
    ]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=1000, max_stops=1, preference=RoutePreference.RECENT)
    assert plan.stops[0].ranked.candidate.offer_id == 2


def test_distance_preference_prefers_closest():
    candidates = [
        _c(1, Category.DISCOUNT, base=1000, distance_m=800.0),
        _c(2, Category.DISCOUNT, base=1000, distance_m=50.0),
    ]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=1000, max_stops=1, preference=RoutePreference.DISTANCE)
    assert plan.stops[0].ranked.candidate.offer_id == 2


def test_preference_does_not_override_budget_constraint():
    # cheapest든 뭐든, 예산 넘는 후보는 여전히 못 담는다.
    candidates = [_c(1, Category.DISCOUNT, base=50000)]
    ranked = rank_candidates(candidates)
    plan = build_route(ranked, budget=1000, max_stops=4, preference=RoutePreference.CHEAPEST)
    assert plan.stops == []
    assert plan.fits_budget is False
