from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    InvalidVisitReadingsError,
    LowGpsAccuracyError,
    LowGpsAccuracyVisitError,
    PlacePublicNotFoundError,
    StaleLocationReadingError,
    TooFarFromStoreError,
)
from app.core.spatial import haversine_m
from app.domain.enums import BusinessStatus, XpReason
from app.domain.place import Place
from app.domain.store_visit import PlaceRecommendation, PlaceVisit, StoreInterest, StoreStatusUpdate
from app.gamification.service import award_xp

MAX_VISIT_DISTANCE_M = 50.0
MAX_GPS_ACCURACY_M = 100.0  # 이보다 오차가 크면 위치를 신뢰할 수 없다고 본다(발견하기 전용)

# 클라이언트 시각을 얼마나 신뢰할지의 상한 — 이보다 미래거나 오래된 timestamp는
# 재전송/캐시값 의심으로 거부한다(§10/§11, 서버가 클라이언트 값을 그대로 신뢰하지
# 않는다는 원칙의 최소 구현).
_MAX_FUTURE_SKEW_SEC = 30.0
_MAX_READING_AGE_SEC = 300.0


def _to_kst_date(ts: datetime) -> date:
    return (ts + timedelta(hours=9)).date()


async def _load_place_and_measure(
    session: AsyncSession, place_id: int, lat: float, lng: float
) -> tuple[Place, float]:
    """place 존재 확인 + 서버가 직접 거리를 재계산 — submit_status_update(발견하기)와
    submit_visit(방문 기록)이 공유한다(§10: 클라이언트가 보낸 distance는 최종
    판정값으로 쓰지 않고 서버가 항상 다시 계산한다)."""
    place = await session.get(Place, place_id)
    if place is None:
        raise PlacePublicNotFoundError()
    point = to_shape(place.geom)
    distance = haversine_m(lat, lng, point.y, point.x)
    return place, distance


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
    _, distance = await _load_place_and_measure(session, place_id, lat, lng)

    if accuracy_m is not None and accuracy_m > MAX_GPS_ACCURACY_M:
        raise LowGpsAccuracyError()

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
        xp_awarded = await award_xp(session, user_id, XpReason.STORE_VISIT_UPDATE, place_id=place_id)

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
) -> tuple[bool, int, int]:
    """매장 추천(👍). AI 절약 리포트의 "판단 근거"에 실제 집계로 반영되는, 사용자당
    1회만 유효한 실제 신호다. 성장치 재조정(2026-09-01)부터 최초 추천에도 XP를
    지급한다 — 지금까지는 이 행동에만 보상이 없었다."""
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

    xp_awarded = 0
    if is_new:
        xp_awarded = await award_xp(session, user_id, XpReason.PLACE_RECOMMEND, place_id=place_id)

    count = (
        await session.execute(
            select(func.count())
            .select_from(PlaceRecommendation)
            .where(PlaceRecommendation.place_id == place_id)
        )
    ).scalar_one()
    return is_new, count, xp_awarded


@dataclass
class VisitReading:
    lat: float
    lng: float
    accuracy_m: float
    client_timestamp: datetime


@dataclass
class VisitResult:
    place_id: int
    distance_m: float
    already_today: bool
    xp_awarded: int
    visit_count: int


def _validate_reading_timestamp(reading: VisitReading, now: datetime) -> None:
    """§10/§11 — 서버가 클라이언트 timestamp를 그대로 신뢰하지 않는다. 미래거나
    너무 오래된 값은 재전송/캐시값 의심으로 거부."""
    ts = reading.client_timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    skew = (ts - now).total_seconds()
    if skew > _MAX_FUTURE_SKEW_SEC or -skew > _MAX_READING_AGE_SEC:
        raise StaleLocationReadingError()


async def submit_visit(
    session: AsyncSession,
    user_id: str,
    place_id: int,
    readings: list[VisitReading],
) -> VisitResult:
    """방문 GPS 인증 공식 기준(§4~§12, 2026-09-01 사용자 확정)의 서버 판정 순서
    그대로 구현한다:
      1. 인증 사용자 확인      — 호출부(RequireUserDep)에서 이미 끝남
      2. place 존재 확인
      3. 좌표 유효성 확인      — 스키마 레벨(Pydantic) + 여기서 재확인
      4. GPS accuracy 확인     — 30m 초과 거부(발견하기의 100m보다 엄격)
      5. 서버에서 거리 재계산  — _load_place_and_measure, 클라이언트 distance는 안 씀
      6. distance <= 50m 확인
      7. 위치 측정 timestamp 확인
      8. 중복 방문 확인        — already_today면 XP 0으로 200 응답(에러 아님)
      9. 방문 저장             — UNIQUE(user_id,place_id,visit_date) 위반 시
                                  IntegrityError를 잡아 이긴 쪽을 재조회(레이스 방어)
      10. 성장치 지급
    §7의 "2회 연속 측정"은 여기서 두 읽음 모두 4~7단계를 통과하는지 각각
    검증하고, 두 timestamp 간격이 너무 짧으면(캐시 좌표 재사용 의심) 거부한다 —
    저장은 마지막(가장 최근) 읽음 기준."""
    if len(readings) != settings.visit_min_consecutive_readings:
        raise InvalidVisitReadingsError()

    now = datetime.now(timezone.utc)
    place = None
    last_distance = 0.0
    for reading in readings:
        _validate_reading_timestamp(reading, now)
        place, distance = await _load_place_and_measure(session, place_id, reading.lat, reading.lng)
        if reading.accuracy_m > settings.visit_gps_accuracy_max_m:
            raise LowGpsAccuracyVisitError()
        if distance > settings.visit_distance_max_m:
            raise TooFarFromStoreError(
                f"매장에서 약 {round(distance)}m 떨어져 있습니다 (50m 이내에서만 방문 기록이 가능합니다)"
            )
        last_distance = distance

    ts0 = readings[0].client_timestamp
    ts1 = readings[-1].client_timestamp
    if ts0.tzinfo is None:
        ts0 = ts0.replace(tzinfo=timezone.utc)
    if ts1.tzinfo is None:
        ts1 = ts1.replace(tzinfo=timezone.utc)
    gap = abs((ts1 - ts0).total_seconds())
    if gap < settings.visit_reading_min_gap_sec:
        raise InvalidVisitReadingsError()

    assert place is not None  # readings는 길이 검증을 통과했으므로 최소 1회 순회함
    latest = readings[-1]
    visit_date = _to_kst_date(now)

    async def _existing_visit() -> PlaceVisit | None:
        return (
            await session.execute(
                select(PlaceVisit).where(
                    PlaceVisit.user_id == user_id,
                    PlaceVisit.place_id == place_id,
                    PlaceVisit.visit_date == visit_date,
                )
            )
        ).scalar_one_or_none()

    existing = await _existing_visit()
    if existing is not None:
        return VisitResult(
            place_id=place_id, distance_m=round(last_distance, 1), already_today=True,
            xp_awarded=0, visit_count=await _get_visit_count(session, user_id),
        )

    session.add(
        PlaceVisit(
            user_id=user_id,
            place_id=place_id,
            lat=latest.lat,
            lng=latest.lng,
            gps_accuracy=latest.accuracy_m,
            distance_at_visit=last_distance,
            visit_date=visit_date,
            client_timestamp=ts1,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        # 동시 요청 레이스 — 유니크 인덱스가 최종 방어선(§14). 진 쪽은 롤백 후
        # 이긴 쪽 결과를 그대로 읽어 반환한다(price_discovery/user_digest와 같은
        # 패턴).
        await session.rollback()
        return VisitResult(
            place_id=place_id, distance_m=round(last_distance, 1), already_today=True,
            xp_awarded=0, visit_count=await _get_visit_count(session, user_id),
        )

    xp_awarded = await award_xp(session, user_id, XpReason.PLACE_VISIT, place_id=place_id)
    return VisitResult(
        place_id=place_id,
        distance_m=round(last_distance, 1),
        already_today=False,
        xp_awarded=xp_awarded,
        visit_count=await _get_visit_count(session, user_id),
    )


async def _get_visit_count(session: AsyncSession, user_id: str) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(PlaceVisit).where(PlaceVisit.user_id == user_id)
        )
    ).scalar_one()


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
