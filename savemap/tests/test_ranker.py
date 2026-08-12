from app.domain.enums import Category, Layer
from app.engine.models import OfferCandidate
from app.engine.ranker import dedupe_by_place, rank_candidates


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
