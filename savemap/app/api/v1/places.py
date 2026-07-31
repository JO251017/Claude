from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
from app.api.schemas.merchant import MenuItemResponse
from app.api.schemas.place import (
    MenuPriceComparisonResponse,
    MenuReportCreate,
    StatusUpdateCreate,
    StatusUpdateResponse,
)
from app.core.errors import PlacePublicNotFoundError
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.price_comparison import compare_menu_item
from app.sources.community_menu.service import find_or_create_place, submit_menu_report
from app.sources.store_visit.service import submit_status_update

router = APIRouter(tags=["places"], prefix="/places")


@router.get("/{place_id}/menu-items", response_model=list[MenuPriceComparisonResponse])
async def list_place_menu_items(
    place_id: int,
    lat: float = Query(...),
    lng: float = Query(...),
    radius_km: float = Query(default=3.0),
    session: AsyncSession = SessionDep,
) -> list[MenuPriceComparisonResponse]:
    place = await session.get(Place, place_id)
    if place is None:
        raise PlacePublicNotFoundError()

    items = list(
        (await session.execute(select(MenuItem).where(MenuItem.place_id == place_id)))
        .scalars()
        .all()
    )
    comparisons = [await compare_menu_item(session, item, lat, lng, radius_km) for item in items]
    return [
        MenuPriceComparisonResponse(
            menu_item_id=c.menu_item_id,
            name=c.name,
            store_price=c.store_price,
            region_average=c.region_average,
            region_median=c.region_median,
            sample_count=c.sample_count,
            savings_amount=c.savings_amount,
            savings_rate=c.savings_rate,
            reliable=c.reliable,
            benchmark_source=c.benchmark_source,
            benchmark_price=c.benchmark_price,
        )
        for c in comparisons
    ]


@router.post("/menu-reports", response_model=MenuItemResponse, status_code=201)
async def create_menu_report(
    payload: MenuReportCreate,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> MenuItemResponse:
    """카카오맵으로만 발견된(아직 SaveMap에 없는) 매장의 메뉴를, 실제로 그 메뉴판을
    본 사용자가 사진으로 제보한다. 제보자가 그 매장의 사업자가 되는 게 아니므로
    사업자 콘솔(RequireUserDep + 소유권 확인)과 달리 로그인만 하면 누구나 쓸 수 있다."""
    place = await find_or_create_place(
        session,
        kakao_place_id=payload.kakao_place_id,
        name=payload.place_name,
        address=payload.address,
        phone=payload.phone,
        lat=payload.lat,
        lng=payload.lng,
    )
    item, cmp = await submit_menu_report(
        session, place, name=payload.name, price=payload.price, source_url=payload.source_url
    )
    return MenuItemResponse(
        id=item.id,
        place_id=item.place_id,
        name=item.name,
        price=float(item.price),
        source_url=item.source_url,
        verified_at=item.verified_at,
        region_median=cmp.region_median,
        sample_count=cmp.sample_count,
        savings_amount=cmp.savings_amount,
        savings_rate=cmp.savings_rate,
        reliable=cmp.reliable,
        benchmark_source=cmp.benchmark_source,
        benchmark_price=cmp.benchmark_price,
        listed_on_map=bool(cmp.savings_amount and cmp.savings_amount > 0),
    )


@router.post("/{place_id}/status-updates", response_model=StatusUpdateResponse, status_code=201)
async def create_status_update(
    place_id: int,
    payload: StatusUpdateCreate,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> StatusUpdateResponse:
    result = await submit_status_update(
        session,
        user_id,
        place_id,
        payload.status,
        payload.lat,
        payload.lng,
        payload.accuracy_m,
    )
    return StatusUpdateResponse(
        place_id=result.place_id,
        status=result.status,
        distance_m=result.distance_m,
        is_new_interest=result.is_new_interest,
        interest_count=result.interest_count,
        xp_awarded=result.xp_awarded,
    )
