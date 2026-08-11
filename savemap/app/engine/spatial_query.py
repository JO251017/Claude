from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.spatial import WGS84_SRID
from app.domain.offer import Offer
from app.domain.place import Place


async def query_within_radius(
    session: AsyncSession, lat: float, lng: float, radius_km: float
) -> list[tuple[Offer, Place, float]]:
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), WGS84_SRID)
    place_geog = cast(Place.geom, Geography)
    point_geog = cast(point, Geography)
    distance = func.ST_Distance(place_geog, point_geog).label("distance_m")
    stmt = (
        select(Offer, Place, distance)
        .join(Place, Offer.place_id == Place.id)
        .options(selectinload(Offer.payment_benefits))
        .where(func.ST_DWithin(place_geog, point_geog, radius_km * 1000.0))
        .order_by(distance)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1], float(row[2])) for row in rows]


async def query_places_without_offer(
    session: AsyncSession, lat: float, lng: float, radius_km: float, limit: int = 30
) -> list[tuple[Place, float]]:
    """Offer(가격/혜택)가 아직 하나도 없는 Place 중 반경 안에 있는 것들을 찾는다 — 인허가
    데이터로 미리 깔아둔 Place가 대표적이다. query_within_radius는 Offer가 있어야만
    결과에 포함시키므로, 이 함수 없이는 이런 Place가 지도 어디에도 뜨지 않는다
    (Place는 DB에 있는데 검색 결과·발견 목록 둘 다에서 빠지는 실제 문제가 있었다)."""
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), WGS84_SRID)
    place_geog = cast(Place.geom, Geography)
    point_geog = cast(point, Geography)
    distance = func.ST_Distance(place_geog, point_geog).label("distance_m")
    stmt = (
        select(Place, distance)
        .where(~Place.offers.any())
        .where(func.ST_DWithin(place_geog, point_geog, radius_km * 1000.0))
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], float(row[1])) for row in rows]
