from dataclasses import dataclass
from datetime import datetime, timezone

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import LowGpsAccuracyError, PlacePublicNotFoundError, TooFarFromStoreError
from app.core.spatial import haversine_m
from app.domain.enums import BusinessStatus, XpReason
from app.domain.place import Place
from app.domain.store_visit import PlaceRecommendation, StoreInterest, StoreStatusUpdate
from app.gamification.service import award_xp

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

    # "발견" 보상은 절약 비교 데이터 유무와 무관하게 고정 지급한다 — 비교 표본이
    # 없으면 0XP가 되던 예전 방식은 "찾아갈 이유가 안 보인다"는 원인이었다.
    # 최초 관심 등록 시에만 지급해 반복 체크인으로 XP를 계속 얻지 않도록 함.
    xp_awarded = 0
    if is_new_interest:
        xp_awarded = await award_xp(session, user_id, XpReason.STORE_VISIT_UPDATE)

    # 관심도는 고유 사용자 수가 아니라 "이 매장에 실제로 발걸음을 한 횟수"(유동인구)로
    # 보여준다 — 사용자 지시로 반복 방문도 계속 늘어나야 한다.
    interest_count = (
        await session.execute(
            select(func.count())
            .select_from(StoreStatusUpdate)
            .where(StoreStatusUpdate.place_id == place_id)
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


async def get_discover_counts(session: AsyncSession, place_ids: list[int]) -> dict[int, int]:
    """검색 결과에 방문 전부터 "N명이 발견했어요"를 보여주기 위한 매장별 누적 발견(체크인) 수."""
    if not place_ids:
        return {}
    rows = (
        await session.execute(
            select(StoreStatusUpdate.place_id, func.count())
            .where(StoreStatusUpdate.place_id.in_(place_ids))
            .group_by(StoreStatusUpdate.place_id)
        )
    ).all()
    return {place_id: count for place_id, count in rows}


async def get_latest_status(
    session: AsyncSession, place_ids: list[int]
) -> dict[int, BusinessStatus]:
    """매장별 가장 최근 사용자 체크인 영업 상태 — 실제 체크인이 없으면 그 매장은
    딕셔너리에 없다(모른다는 뜻이지, 영업 중이라고 지어내지 않는다)."""
    if not place_ids:
        return {}
    rank = (
        func.row_number()
        .over(partition_by=StoreStatusUpdate.place_id, order_by=StoreStatusUpdate.created_at.desc())
        .label("rn")
    )
    subq = (
        select(StoreStatusUpdate.place_id, StoreStatusUpdate.status, rank)
        .where(StoreStatusUpdate.place_id.in_(place_ids))
        .subquery()
    )
    rows = (
        await session.execute(
            select(subq.c.place_id, subq.c.status).where(subq.c.rn == 1)
        )
    ).all()
    return {place_id: status for place_id, status in rows}


async def submit_recommendation(
    session: AsyncSession, user_id: str, place_id: int
) -> tuple[bool, int]:
    """매장 추천(👍). AI 절약 리포트의 "판단 근거"에 실제 집계로 반영되는, 사용자당
    1회만 유효한 실제 신호다."""
    place = await session.get(Place, place_id)
    if place is None:
        raise PlacePublicNotFoundError()

    existing = (
        await session.execute(
            select(PlaceRecommendation).where(
                PlaceRecommendation.user_id == user_id, PlaceRecommendation.place_id == place_id
            )
        )
    ).scalar_one_or_none()
    is_new = existing is None
    if is_new:
        session.add(PlaceRecommendation(user_id=user_id, place_id=place_id))
        await session.commit()

    count = (
        await session.execute(
            select(func.count())
            .select_from(PlaceRecommendation)
            .where(PlaceRecommendation.place_id == place_id)
        )
    ).scalar_one()
    return is_new, count


async def get_recommend_counts(session: AsyncSession, place_ids: list[int]) -> dict[int, int]:
    if not place_ids:
        return {}
    rows = (
        await session.execute(
            select(PlaceRecommendation.place_id, func.count())
            .where(PlaceRecommendation.place_id.in_(place_ids))
            .group_by(PlaceRecommendation.place_id)
        )
    ).all()
    return {place_id: count for place_id, count in rows}
