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
    SignatureMenuItem,
)
from app.core.config import settings
from app.core.errors import RadiusOutOfRangeError
from app.domain.enums import Category, PaymentMethodType
from app.engine.benefit_combiner import combine
from app.engine.discovery import discover_nearby_places
from app.engine.models import OfferCandidate, PaymentBenefit
from app.engine.price_comparison import list_menu_items_by_place
from app.engine.ranker import dedupe_by_place, rank_candidates
from app.engine.rule_filter import rule_filter
from app.engine.savings_report import build_savings_report
from app.engine.spatial_query import query_places_without_offer, query_within_radius
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
        menu_item_id=offer.menu_item_id,
        benchmark_source=offer.benchmark_source,
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

    rows = await query_within_radius(session, lat, lng, radius, row_limit=settings.search_row_fetch_limit)
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

    # 매장 단위 중복 제거 + 응답 상한(search_max_results)까지 한 번에 적용한다 —
    # 밀집 지역(착한가격업소 등으로 반경 안에 수백 곳이 잡히는 경우)에서 응답이
    # 무한정 커지고 이 아래 메뉴 조회까지 그 수만큼 늘어나는 걸 막는다.
    deduped = dedupe_by_place(ranked, max_results=settings.search_max_results)
    seen_places = {r.candidate.place_id for r in deduped}

    # 대표메뉴: 실제 등록된 메뉴 가격에서만 뽑는다 — 대표 오퍼에 연결된 메뉴가 있으면
    # 그것(절약이 가장 큰 메뉴), 없으면 가장 먼저 등록된 메뉴. 등록된 메뉴가 하나도
    # 없으면 표시하지 않는다 (지어내지 않기).
    menu_items_by_place = await list_menu_items_by_place(session, list(seen_places))

    results = []
    for r in deduped:
        c = r.candidate
        place_items = menu_items_by_place.get(c.place_id, [])
        signature = next(
            (item for item in place_items if item.id == c.menu_item_id),
            place_items[0] if place_items else None,
        )
        report = build_savings_report(
            savings_rate=r.breakdown.savings_rate,
            discover_count=c.discover_count,
            dining_count=c.dining_count,
            recommend_count=c.recommend_count,
            verification_count=c.verification_count,
            last_verified_at=c.last_verified_at,
            # 이전엔 total_savings > 0이면 무조건 "region"으로 간주해서, AI 추정
            # 통상가로 계산된 절약에도 "주변 매장 실측 가격 데이터 반영"이라고
            # 잘못 말하는 문제가 있었다 — Offer에 저장된 실제 출처를 그대로 쓴다.
            benchmark_source=c.benchmark_source,
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
                signature_menu=(
                    SignatureMenuItem(name=signature.name, price=float(signature.price))
                    if signature
                    else None
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
                savings_source=c.benchmark_source,
                expires_at=c.expires_at,
                trust_score=c.trust_score,
                verification_count=c.verification_count,
                last_verified_at=c.last_verified_at,
                discover_count=c.discover_count,
                dining_count=c.dining_count,
                score=round(r.score, 4),
            )
        )

    # Offer가 아직 없어 위 results에는 못 들어간 SaveMap Place(인허가 데이터 등으로
    # 미리 깔아둔 것) — 이것도 안 챙기면 DB에 Place가 있어도 지도 어디에도 안 뜬다.
    no_offer_rows = await query_places_without_offer(session, lat, lng, radius)
    no_offer_coords: list[tuple[float, float]] = []
    no_offer_items: list[DiscoveredPlaceItem] = []
    for place, distance_m in no_offer_rows:
        point = to_shape(place.geom)
        no_offer_coords.append((point.y, point.x))
        no_offer_items.append(
            DiscoveredPlaceItem(
                place_id=place.id,
                kakao_place_id=place.kakao_place_id,
                place_name=place.name,
                address=place.address,
                category_name=place.category_name,
                phone=place.phone,
                distance_m=round(distance_m, 1),
                lat=point.y,
                lng=point.x,
                kakao_url=(
                    f"https://place.map.kakao.com/{place.kakao_place_id}"
                    if place.kakao_place_id
                    else f"https://map.kakao.com/link/search/{quote(place.name)}"
                ),
            )
        )

    # 카카오 실시간 검색은 위 두 소스(가격 있는 results + DB의 무가격 Place)와 겹치는
    # 곳은 중복 표시하지 않도록 둘 다 existing_coords로 넘긴다.
    discovered = await discover_nearby_places(
        lat, lng, radius, existing_coords=[(r.lat, r.lng) for r in results] + no_offer_coords
    )
    kakao_discovered_items = [
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
    discovered_places = no_offer_items + kakao_discovered_items

    return SearchResponse(
        count=len(results), radius_km=radius, results=results, discovered_places=discovered_places
    )
