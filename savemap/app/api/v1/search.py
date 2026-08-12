from urllib.parse import quote

from fastapi import APIRouter, Query
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.api.schemas.search import DiscoveredPlaceItem, SearchResponse
from app.core.config import settings
from app.core.errors import RadiusOutOfRangeError
from app.domain.enums import Category, PaymentMethodType
from app.engine.benefit_combiner import combine
from app.engine.candidate_builder import build_candidate
from app.engine.discovery import discover_nearby_places
from app.engine.price_comparison import list_menu_items_by_place
from app.engine.ranker import dedupe_by_place, rank_candidates
from app.engine.result_assembly import build_search_result_item
from app.engine.rule_filter import rule_filter
from app.engine.spatial_query import query_places_without_offer, query_within_radius
from app.gamification.service import get_dining_counts
from app.sources.store_visit.service import (
    get_discover_counts,
    get_latest_status,
    get_recommend_counts,
)
from app.sources.user_verification.service import get_offer_trust_map

router = APIRouter(tags=["search"])


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

    candidates = [build_candidate(o, p, d) for o, p, d in rows]

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

    results = [
        build_search_result_item(r, menu_items_by_place, latest_status) for r in deduped
    ]

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
