from urllib.parse import quote

from fastapi import APIRouter, Query
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.api.schemas.search import (
    DiscoveredPlaceItem,
    SavingsReportItem,
    SearchResponse,
    SearchResultItem,
)
from app.core.config import settings
from app.core.errors import RadiusOutOfRangeError
from app.domain.enums import Category, PaymentMethodType
from app.engine.benefit_combiner import combine
from app.engine.discovery import discover_nearby_places
from app.engine.models import OfferCandidate, PaymentBenefit
from app.engine.ranker import rank_candidates
from app.engine.rule_filter import rule_filter
from app.engine.savings_report import build_savings_report
from app.engine.spatial_query import query_within_radius
from app.gamification.service import get_dining_counts
from app.sources.store_visit.service import (
    get_discover_counts,
    get_latest_status,
    get_recommend_counts,
)
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
        place_category_name=place.category_name,
        place_kakao_id=place.kakao_place_id,
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
    recommend_counts = await get_recommend_counts(session, place_ids)
    latest_status = await get_latest_status(session, place_ids)
    for c in candidates:
        score, count, last_at = trust_map.get(c.offer_id, (0.5, 0, None))
        c.trust_score = score
        c.verification_count = count
        c.last_verified_at = last_at
        # AI 절약 리포트의 "판단 근거"는 전부 실제 사용자 행동 기록 그대로만 쓴다.
        c.discover_count = discover_counts.get(c.place_id, 0)
        c.dining_count = dining_counts.get(c.place_id, 0)
        c.recommend_count = recommend_counts.get(c.place_id, 0)

    combine(candidates, set(payment_methods))
    ranked = rank_candidates(candidates)

    # 메뉴 하나 등록될 때마다 오퍼가 하나씩 생기므로, 여기서 걸러주지 않으면 매장 하나가
    # 메뉴 개수만큼 마커/카드로 쪼개져서 뜬다 — SaveMap은 메뉴가 아니라 매장 단위 절약
    # 리포트를 보여주는 서비스이므로, 매장당 가장 점수 높은 오퍼 하나만 대표로 남긴다.
    seen_places: set[int] = set()
    deduped = []
    for r in ranked:
        if r.candidate.place_id in seen_places:
            continue
        seen_places.add(r.candidate.place_id)
        deduped.append(r)

    results = []
    for r in deduped:
        c = r.candidate
        report = build_savings_report(
            savings_rate=r.breakdown.savings_rate,
            discover_count=c.discover_count,
            dining_count=c.dining_count,
            recommend_count=c.recommend_count,
            verification_count=c.verification_count,
            last_verified_at=c.last_verified_at,
            benchmark_source="region" if r.breakdown.total_savings > 0 else None,
        )
        status = latest_status.get(c.place_id)
        results.append(
            SearchResultItem(
                offer_id=c.offer_id,
                place_id=c.place_id,
                place_name=c.place_name,
                category_name=c.place_category_name,
                business_status=status.value if status else None,
                report=SavingsReportItem(
                    score=report.score,
                    grade=report.grade,
                    confidence_tier=report.confidence_tier,
                    confidence_stars=report.confidence_stars,
                    confidence_label=report.confidence_label,
                    reasons=report.reasons,
                    one_line=report.one_line,
                ),
                recommend_count=c.recommend_count,
                kakao_url=(
                    f"https://place.map.kakao.com/{c.place_kakao_id}"
                    if c.place_kakao_id
                    else f"https://map.kakao.com/link/search/{quote(c.place_name)}"
                ),
                address=c.place_address,
                phone=c.place_phone,
                category=c.category,
                distance_m=round(c.distance_m, 1),
                lat=c.lat,
                lng=c.lng,
                base_price=r.breakdown.base_price,
                final_price=r.breakdown.final_price,
                total_savings=r.breakdown.total_savings,
                savings_rate=r.breakdown.savings_rate,
                expires_at=c.expires_at,
                trust_score=c.trust_score,
                verification_count=c.verification_count,
                last_verified_at=c.last_verified_at,
                discover_count=c.discover_count,
                dining_count=c.dining_count,
                score=round(r.score, 4),
            )
        )

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
