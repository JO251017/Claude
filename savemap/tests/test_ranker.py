from app.domain.enums import Category, Layer
from app.engine.models import OfferCandidate
from app.engine.ranker import rank_candidates


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
