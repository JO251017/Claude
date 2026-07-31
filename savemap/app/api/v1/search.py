from fastapi import APIRouter, Query
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.api.schemas.search import DiscoveredPlaceItem, SearchResponse, SearchResultItem
from app.core.config import settings
from app.core.errors import RadiusOutOfRangeError
from app.domain.enums import Category, PaymentMethodType
from app.engine.benefit_combiner import combine
from app.engine.discovery import discover_nearby_places
from app.engine.models import OfferCandidate, PaymentBenefit
from app.engine.ranker import rank_candidates
from app.engine.rule_filter import rule_filter
from app.engine.spatial_query import query_within_radius
from app.gamification.service import get_dining_counts
from app.sources.store_visit.service import get_discover_counts
from app.sources.user_verification.service import get_offer_trust_map

router = APIRouter(tags=["search"])


def _to_candidate(offer, place, distance_m: float) -> OfferCandidate:
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
        title=offer.title,
        payment_benefits=[
            PaymentBenefit(
                method_type=b.method_type,
                rate=float(b.benefit_rate or 0.0),
                amount=float(b.benefit_amount or 0.0),
            )
            for b in offer.payment_benefits
        ],
    )


@router.get("/search", response_model=SearchResponse)
async def search(
    lat: float = Query(...),
    lng: float = Query(...),
    radius_km: float | None = Query(default=None),
    category: Category | None = Query(default=None),
    payment_methods: list[PaymentMethodType] = Query(default_factory=list),
    session: AsyncSession = SessionDep,
) -> SearchResponse:
    radius = radius_km or settings.search_default_radius_km
    if radius <= 0 or radius > settings.search_max_radius_km:
        raise RadiusOutOfRangeError()

    rows = await query_within_radius(session, lat, lng, radius)
    rows = rule_filter(rows, category=category)

    candidates = [_to_candidate(o, p, d) for o, p, d in rows]

    trust_map = await get_offer_trust_map(session, [c.offer_id for c in candidates])
    place_ids = [c.place_id for c in candidates]
    discover_counts = await get_discover_counts(session, place_ids)
    dining_counts = await get_dining_counts(session, place_ids)
    for c in candidates:
        score, count, last_at = trust_map.get(c.offer_id, (0.5, 0, None))
        c.trust_score = score
        c.verification_count = count
        c.last_verified_at = last_at
        # 방문 전에도 "N명이 발견 · N번 식사 인증"을 보여줘서 찾아갈 이유를 사회적
        # 증거로 미리 제시한다 (지어내지 않기: 둘 다 실제 사용자 행동 기록 그대로).
        c.discover_count = discover_counts.get(c.place_id, 0)
        c.dining_count = dining_counts.get(c.place_id, 0)

    combine(candidates, set(payment_methods))
    ranked = rank_candidates(candidates)

    results = [
        SearchResultItem(
            offer_id=r.candidate.offer_id,
            place_id=r.candidate.place_id,
            place_name=r.candidate.place_name,
            title=r.candidate.title,
            address=r.candidate.place_address,
            phone=r.candidate.place_phone,
            category=r.candidate.category,
            distance_m=round(r.candidate.distance_m, 1),
            lat=r.candidate.lat,
            lng=r.candidate.lng,
            base_price=r.breakdown.base_price,
            final_price=r.breakdown.final_price,
            total_savings=r.breakdown.total_savings,
            savings_rate=r.breakdown.savings_rate,
            expires_at=r.candidate.expires_at,
            trust_score=r.candidate.trust_score,
            verification_count=r.candidate.verification_count,
            last_verified_at=r.candidate.last_verified_at,
            discover_count=r.candidate.discover_count,
            dining_count=r.candidate.dining_count,
            score=round(r.score, 4),
        )
        for r in ranked
    ]

    discovered = await discover_nearby_places(
        lat, lng, radius, existing_coords=[(r.lat, r.lng) for r in results]
    )
    discovered_places = [
        DiscoveredPlaceItem(
            kakao_place_id=c.place.kakao_place_id,
            place_name=c.place.name,
            address=c.place.address,
            category_name=c.place.category_name,
            phone=c.place.phone,
            distance_m=round(c.distance_m, 1),
            lat=c.place.lat,
            lng=c.place.lng,
            kakao_url=c.place.place_url,
        )
        for c in discovered
    ]

    return SearchResponse(
        count=len(results), radius_km=radius, results=results, discovered_places=discovered_places
    )
