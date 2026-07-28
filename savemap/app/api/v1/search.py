from fastapi import APIRouter, Query
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.api.schemas.search import SearchResponse, SearchResultItem
from app.core.config import settings
from app.core.errors import RadiusOutOfRangeError
from app.domain.enums import Category, PaymentMethodType
from app.engine.benefit_combiner import combine
from app.engine.models import OfferCandidate, PaymentBenefit
from app.engine.ranker import rank_candidates
from app.engine.rule_filter import rule_filter
from app.engine.spatial_query import query_within_radius

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
    combine(candidates, set(payment_methods))
    ranked = rank_candidates(candidates)

    results = [
        SearchResultItem(
            offer_id=r.candidate.offer_id,
            place_name=r.candidate.place_name,
            category=r.candidate.category,
            distance_m=round(r.candidate.distance_m, 1),
            lat=r.candidate.lat,
            lng=r.candidate.lng,
            base_price=r.breakdown.base_price,
            final_price=r.breakdown.final_price,
            total_savings=r.breakdown.total_savings,
            savings_rate=r.breakdown.savings_rate,
            trust_score=r.candidate.trust_score,
            score=round(r.score, 4),
        )
        for r in ranked
    ]
    return SearchResponse(count=len(results), radius_km=radius, results=results)
