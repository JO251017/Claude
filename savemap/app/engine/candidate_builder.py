from geoalchemy2.shape import to_shape

from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.models import OfferCandidate, PaymentBenefit


def build_candidate(offer: Offer, place: Place, distance_m: float) -> OfferCandidate:
    """DB에서 온 (Offer, Place, distance) 한 행을 엔진이 쓰는 OfferCandidate로 바꾼다.
    /search와 /route/suggest가 똑같은 후보 수집 파이프라인(공간쿼리 → rule_filter →
    rank_candidates)을 타므로, 이 변환도 한 곳에만 둔다 — 원래 app/api/v1/search.py에
    있던 _to_candidate를 그대로 옮긴 것."""
    point = to_shape(place.geom)
    return OfferCandidate(
        offer_id=offer.id,
        place_id=place.id,
        place_name=place.name,
        category=offer.category,
        layer=offer.layer,
        distance_m=distance_m,
        base_price=float(offer.base_price or 0.0),
        lat=point.y,
        lng=point.x,
        store_discount=float(offer.store_discount or 0.0),
        expires_at=offer.expires_at,
        place_address=place.address,
        place_phone=place.phone,
        place_category_name=place.category_name,
        place_kakao_id=place.kakao_place_id,
        title=offer.title,
        menu_item_id=offer.menu_item_id,
        benchmark_source=offer.benchmark_source,
        benchmark_sample_count=offer.benchmark_sample_count,
        accepts_local_currency=place.accepts_local_currency,
        payment_benefits=[
            PaymentBenefit(
                method_type=b.method_type,
                rate=float(b.benefit_rate or 0.0),
                amount=float(b.benefit_amount or 0.0),
            )
            for b in offer.payment_benefits
        ],
    )
