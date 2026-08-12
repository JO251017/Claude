from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.api.schemas.route import RouteStopItem, RouteSuggestRequest, RouteSuggestResponse
from app.core.config import settings
from app.core.errors import BudgetOutOfRangeError, RadiusOutOfRangeError
from app.engine.benefit_combiner import combine
from app.engine.candidate_builder import build_candidate
from app.engine.price_comparison import list_menu_items_by_place
from app.engine.ranker import dedupe_by_place, rank_candidates
from app.engine.result_assembly import build_search_result_item
from app.engine.route_planner import build_route, generate_summary
from app.engine.rule_filter import rule_filter
from app.engine.spatial_query import query_within_radius
from app.gamification.service import get_dining_counts
from app.sources.store_visit.service import (
    get_discover_counts,
    get_latest_status,
    get_recommend_counts,
)
from app.sources.user_verification.service import get_offer_trust_map

router = APIRouter(tags=["route"])


@router.post("/route/suggest", response_model=RouteSuggestResponse)
async def suggest_route(
    payload: RouteSuggestRequest,
    session: AsyncSession = SessionDep,
) -> RouteSuggestResponse:
    if not (settings.route_min_budget <= payload.budget <= settings.route_max_budget):
        raise BudgetOutOfRangeError()

    radius = payload.radius_km or settings.search_default_radius_km
    if radius <= 0 or radius > settings.search_max_radius_km:
        raise RadiusOutOfRangeError()

    rows = await query_within_radius(
        session, payload.lat, payload.lng, radius, row_limit=settings.search_row_fetch_limit
    )
    rows = rule_filter(rows, category=payload.category)
    candidates = [build_candidate(o, p, d) for o, p, d in rows]
    combine(candidates, set(payload.payment_methods))

    # 후보 풀(수십~수백개일 수 있음) 단계에서는 trust_score 기본값(0.5, OfferCandidate
    # 기본값)만 쓴다 — /search처럼 모든 후보에 대해 trust/discover/dining 배치쿼리를
    # 돌리면 매 코스 요청마다 그 규모로 조회가 늘어난다. 최종 선택된 스톱(최대
    # route_max_stops개)에만 아래에서 실제 데이터를 붙인다.
    ranked = rank_candidates(candidates)
    deduped = dedupe_by_place(ranked, max_results=settings.search_max_results)

    plan = build_route(deduped, budget=payload.budget, max_stops=settings.route_max_stops)

    stop_items: list[RouteStopItem] = []
    if plan.stops:
        place_ids = [s.ranked.candidate.place_id for s in plan.stops]
        offer_ids = [s.ranked.candidate.offer_id for s in plan.stops]
        trust_map = await get_offer_trust_map(session, offer_ids)
        discover_counts = await get_discover_counts(session, place_ids)
        dining_counts = await get_dining_counts(session, place_ids)
        recommend_counts = await get_recommend_counts(session, place_ids)
        latest_status = await get_latest_status(session, place_ids)
        menu_items_by_place = await list_menu_items_by_place(session, place_ids)

        for s in plan.stops:
            c = s.ranked.candidate
            score, count, last_at = trust_map.get(c.offer_id, (0.5, 0, None))
            c.trust_score = score
            c.verification_count = count
            c.last_verified_at = last_at
            c.discover_count = discover_counts.get(c.place_id, 0)
            c.dining_count = dining_counts.get(c.place_id, 0)
            c.recommend_count = recommend_counts.get(c.place_id, 0)

            item = build_search_result_item(s.ranked, menu_items_by_place, latest_status)
            stop_items.append(RouteStopItem(**item.model_dump(), order=s.order))

    summary, summary_source = await generate_summary(plan, payload.party_size)

    return RouteSuggestResponse(
        fits_budget=plan.fits_budget,
        budget=payload.budget,
        party_size=payload.party_size,
        radius_km=radius,
        stop_count=len(stop_items),
        total_spend=plan.total_spend,
        total_savings=plan.total_savings,
        remaining_budget=plan.remaining_budget,
        stops=stop_items,
        summary=summary,
        summary_source=summary_source,
    )
