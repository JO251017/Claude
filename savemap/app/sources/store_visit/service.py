from dataclasses import dataclass
from datetime import datetime, timezone

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import LowGpsAccuracyError, PlacePublicNotFoundError, TooFarFromStoreError
from app.core.spatial import haversine_m
from app.domain.enums import BusinessStatus, XpReason
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.domain.store_visit import StoreInterest, StoreStatusUpdate
from app.engine.price_comparison import best_expected_savings
from app.gamification.service import award_xp_for_amount

MAX_VISIT_DISTANCE_M = 50.0
MAX_GPS_ACCURACY_M = 100.0  # 이보다 오차가 크면 위치를 신뢰할 수 없다고 본다


@dataclass
class StoreStatusUpdateResult:
    place_id: int
    status: BusinessStatus
    distance_m: float
    is_new_interest: bool
    interest_count: int
    xp_awarded: int


async def submit_status_update(
    session: AsyncSession,
    user_id: str,
    place_id: int,
    status: BusinessStatus,
    lat: float,
    lng: float,
    accuracy_m: float | None = None,
) -> StoreStatusUpdateResult:
    place = await session.get(Place, place_id)
    if place is None:
        raise PlacePublicNotFoundError()

    if accuracy_m is not None and accuracy_m > MAX_GPS_ACCURACY_M:
        raise LowGpsAccuracyError()

    point = to_shape(place.geom)
    distance = haversine_m(lat, lng, point.y, point.x)
    if distance > MAX_VISIT_DISTANCE_M:
        raise TooFarFromStoreError(
            f"매장에서 약 {round(distance)}m 떨어져 있습니다 (50m 이내에서만 방문 인증이 가능합니다)"
        )

    session.add(
        StoreStatusUpdate(
            user_id=user_id, place_id=place_id, status=status, lat=lat, lng=lng, distance_m=distance
        )
    )

    existing_interest = (
        await session.execute(
            select(StoreInterest).where(
                StoreInterest.user_id == user_id, StoreInterest.place_id == place_id
            )
        )
    ).scalar_one_or_none()
    is_new_interest = existing_interest is None
    now = datetime.now(timezone.utc)
    if existing_interest is None:
        session.add(StoreInterest(user_id=user_id, place_id=place_id, last_interested_at=now))
    else:
        existing_interest.last_interested_at = now

    await session.commit()

    # XP는 최초 관심 등록 시에만 지급한다 — 반복 상태 업데이트로 XP를 계속 얻지 않도록 함.
    xp_awarded = 0
    if is_new_interest:
        menu_items = list(
            (await session.execute(select(MenuItem).where(MenuItem.place_id == place_id)))
            .scalars()
            .all()
        )
        expected_savings = await best_expected_savings(session, menu_items, point.y, point.x)
        xp_awarded = await award_xp_for_amount(
            session, user_id, XpReason.STORE_VISIT_UPDATE, expected_savings
        )

    interest_count = (
        await session.execute(
            select(func.count()).select_from(StoreInterest).where(StoreInterest.place_id == place_id)
        )
    ).scalar_one()

    return StoreStatusUpdateResult(
        place_id=place_id,
        status=status,
        distance_m=round(distance, 1),
        is_new_interest=is_new_interest,
        interest_count=interest_count,
        xp_awarded=xp_awarded,
    )
