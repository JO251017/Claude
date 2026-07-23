from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
        .where(func.ST_DWithin(place_geog, point_geog, radius_km * 1000.0))
        .order_by(distance)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1], float(row[2])) for row in rows]
