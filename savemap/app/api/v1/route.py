from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.api.schemas.route import RouteStopItem, RouteSuggestRequest, RouteSuggestResponse
from app.core.config import settings
from app.core.errors import BudgetOutOfRangeError, RadiusOutOfRangeError
from app.domain.enums import Category, RoutePreference
from app.engine.activity_classifier import ACTIVITY_LABELS
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

_PREFERENCE_LABELS: dict[RoutePreference, str] = {
    RoutePreference.CHEAPEST: "최대한 저렴하게",
    RoutePreference.VERIFIED: "검증된 정보 우선",
    RoutePreference.RECENT: "최신 정보 우선",
    RoutePreference.DISTANCE: "이동거리 최소화",
}


def _build_context_note(payload: RouteSuggestRequest) -> str | None:
    """Gemini가 코스를 설명할 때 참고할 "사용자가 뭘 골랐는지" 한 줄 요약. 순수
    UI 텍스트 조립이라 숫자는 하나도 안 들어간다 — route_planner.generate_summary의
    context_note로 그대로 전달된다."""
    parts: list[str] = []
    if payload.activities:
        parts.append("활동: " + ", ".join(ACTIVITY_LABELS[a] for a in payload.activities))
    conditions = []
    if payload.preference:
        conditions.append(_PREFERENCE_LABELS[payload.preference])
    if payload.free_parking_required:
        conditions.append("무료주차 필요")
    if conditions:
        parts.append("조건: " + ", ".join(conditions))
    return " · ".join(parts) if parts else None


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
    # 무료주차는 Category(절약 수단) 값 자체가 "이 오퍼가 무료주차 혜택이다"라는
    # 뜻이라(도메인상 오퍼 하나엔 카테고리가 하나) 지금 데이터 모델에서는 "필요
    # 조건"으로 걸 수 있는 유일한 방법이 이 필터다 — 식사 오퍼가 곁다리로 주차장을
    # 갖고 있어도 그 오퍼의 category가 free_parking이 아니면 지금은 알 수 없다
    # (알려진 v1 한계, ARCHITECTURE.md 참고).
    offer_type = Category.FREE_PARKING if payload.free_parking_required else None
    rows = rule_filter(rows, category=offer_type, activities=payload.activities)
    candidates = [build_candidate(o, p, d) for o, p, d in rows]
    combine(candidates, set(payload.payment_methods))

    # 후보 풀(수십~수백개일 수 있음) 단계에서는 trust_score 기본값(0.5, OfferCandidate
    # 기본값)만 쓴다 — /search처럼 모든 후보에 대해 trust/discover/dining 배치쿼리를
    # 돌리면 매 코스 요청마다 그 규모로 조회가 늘어난다. 최종 선택된 스톱(최대
    # route_max_stops개)에만 아래에서 실제 데이터를 붙인다.
    ranked = rank_candidates(candidates)
    deduped = dedupe_by_place(ranked, max_results=settings.search_max_results)

    if payload.preference in (RoutePreference.VERIFIED, RoutePreference.RECENT):
        # "검증된 정보 우선"/"최신 정보 우선"은 실제 trust_score/last_verified_at이
        # 있어야 의미가 있다 — 아래 for문(선택된 스톱만 enrich)까지 기다리면 이 시점의
        # 후보는 전부 OfferCandidate 기본값(trust_score=0.5, last_verified_at=None)
        # 이라 정렬해봐야 전부 동률이라 조건이 사실상 무효가 된다. 후보 풀은 이미
        # dedupe_by_place(max_results)로 상한이 걸려 있어(최대 search_max_results건)
        # 여기서 배치 조회해도 /search가 매 요청 하는 것과 같은 규모다.
        pool_offer_ids = [r.candidate.offer_id for r in deduped]
        trust_map = await get_offer_trust_map(session, pool_offer_ids)
        for r in deduped:
            score, count, last_at = trust_map.get(r.candidate.offer_id, (0.5, 0, None))
            r.candidate.trust_score = score
            r.candidate.verification_count = count
            r.candidate.last_verified_at = last_at

    plan = build_route(
        deduped,
        budget=payload.budget,
        max_stops=settings.route_max_stops,
        preference=payload.preference,
    )

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

    summary, summary_source = await generate_summary(
        plan, payload.party_size, context_note=_build_context_note(payload)
    )

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
