from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
from app.api.schemas.merchant import MenuItemAnalyzeResponse, MenuItemResponse
from app.api.schemas.place import (
    MenuPriceComparisonResponse,
    MenuReportBatchCreate,
    RecommendationResponse,
    StatusUpdateCreate,
    StatusUpdateResponse,
)
from app.core.errors import PlacePublicNotFoundError
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.menu_photo_analysis import analyze_menu_photo_upload
from app.engine.price_comparison import compare_menu_item
from app.sources.community_menu.service import find_or_create_place, submit_menu_report_batch
from app.sources.store_visit.service import submit_recommendation, submit_status_update

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


@router.post("/menu-reports/analyze", response_model=MenuItemAnalyzeResponse)
async def analyze_menu_report_photo(
    image: UploadFile = File(...),
    user_id: str = RequireUserDep,
) -> MenuItemAnalyzeResponse:
    """발견된(아직 가격 정보 없는) 매장의 메뉴판 사진을 실제로 본 사용자가 분석
    요청한다. 사업자 인증 불필요 — create_menu_report와 같은 인증 수준(로그인만).
    예전엔 프론트가 이 목적으로 사업자 콘솔 전용 엔드포인트(/merchant/menu-items/
    analyze)를 재사용했는데, 사업자 인증 접근 제어(2026-08-13, require_merchant_
    verified)가 그 엔드포인트에 걸리면서 일반 사용자가 막히는 회귀가 생겼다 —
    이 전용 엔드포인트로 분리해서 고친다(사용자 지시: "메뉴판등록은... 사용자들이
    등록하도록 바꿔"). DB 저장은 안 함(확인 전 단계) — 저장은 아래
    /menu-reports를 별도 호출."""
    return await analyze_menu_photo_upload(image)


@router.post("/menu-reports", response_model=list[MenuItemResponse], status_code=201)
async def create_menu_report(
    payload: MenuReportBatchCreate,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> list[MenuItemResponse]:
    """카카오맵으로만 발견된(아직 SaveMap에 없는) 매장의 메뉴를, 실제로 그 메뉴판을
    본 사용자가 사진으로 제보한다. 사진 한 장에서 메뉴가 여럿 나올 수 있어 배치로
    받는다. 제보자가 그 매장의 사업자가 되는 게 아니므로 사업자 콘솔(소유권 확인)과
    달리 로그인만 하면 누구나 쓸 수 있다. 예전엔 매장당 이 배치 전체가 최초 1회만
    허용됐지만(2026-08-13), 사업자 등록을 비활성화하고 이 경로를 유일한 메뉴 등록
    수단으로 삼으면서(사용자 지시, 2026-08-18) 항목 단위로 계속 갱신을 받는다 —
    같은 가격이면 무시(unchanged), 다르면 AI가 사진·최신성을 보고 판단
    (updated/rejected). 자세한 상태 분기는 submit_menu_report_batch 참고."""
    place = await find_or_create_place(
        session,
        place_id=payload.place_id,
        kakao_place_id=payload.kakao_place_id,
        name=payload.place_name,
        address=payload.address,
        phone=payload.phone,
        lat=payload.lat,
        lng=payload.lng,
        category_name=payload.category_name,
    )
    results = await submit_menu_report_batch(
        session, user_id, place, [(i.name, i.price, i.source_url) for i in payload.items]
    )
    responses = []
    for item, cmp, xp_awarded, status, review_note in results:
        responses.append(
            MenuItemResponse(
                id=item.id,
                place_id=item.place_id,
                name=item.name,
                price=float(item.price),
                source_url=item.source_url,
                verified_at=item.verified_at,
                # rejected는 cmp가 없다(기존 가격을 그대로 두므로 새로 비교할 게
                # 없음) — 지도 노출 여부도 이전 상태 그대로이므로 listed_on_map은
                # False로 두고 프론트가 status/review_note로 안내 문구를 판단한다.
                region_median=cmp.region_median if cmp else None,
                sample_count=cmp.sample_count if cmp else 0,
                savings_amount=cmp.savings_amount if cmp else None,
                savings_rate=cmp.savings_rate if cmp else None,
                reliable=cmp.reliable if cmp else False,
                benchmark_source=cmp.benchmark_source if cmp else None,
                benchmark_price=cmp.benchmark_price if cmp else None,
                listed_on_map=bool(cmp and cmp.savings_amount and cmp.savings_amount > 0),
                xp_awarded=xp_awarded,
                status=status,
                review_note=review_note,
            )
        )
    return responses


@router.post("/{place_id}/recommendations", response_model=RecommendationResponse, status_code=201)
async def create_recommendation(
    place_id: int,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> RecommendationResponse:
    is_new, count = await submit_recommendation(session, user_id, place_id)
    return RecommendationResponse(place_id=place_id, is_new=is_new, recommend_count=count)


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
