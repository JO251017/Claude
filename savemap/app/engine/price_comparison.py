import statistics
from dataclasses import dataclass

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.spatial import WGS84_SRID
from app.domain.menu_item import MenuItem
from app.domain.place import Place

# 이 개수 미만이면 평균/중앙값을 신뢰할 수 없다고 보고 "비교 데이터 부족"으로 표시한다
# (기획서 §5). 사용자 지시로 2건까지는 비교 가능하다고 판단.
MIN_RELIABLE_SAMPLE = 2


@dataclass
class MenuPriceComparison:
    menu_item_id: int
    name: str
    store_price: float
    place_id: int
    region_average: float | None
    region_median: float | None
    sample_count: int
    savings_amount: float | None
    savings_rate: float | None
    reliable: bool


async def _region_prices(
    session: AsyncSession, name: str, lat: float, lng: float, radius_km: float
) -> list[float]:
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), WGS84_SRID)
    place_geog = cast(Place.geom, Geography)
    point_geog = cast(point, Geography)
    stmt = (
        select(MenuItem.price)
        .join(Place, MenuItem.place_id == Place.id)
        .where(
            func.lower(func.trim(MenuItem.name)) == name.strip().lower(),
            func.ST_DWithin(place_geog, point_geog, radius_km * 1000.0),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [float(r) for r in rows]


async def compare_menu_item(
    session: AsyncSession, menu_item: MenuItem, lat: float, lng: float, radius_km: float = 3.0
) -> MenuPriceComparison:
    prices = await _region_prices(session, menu_item.name, lat, lng, radius_km)
    sample_count = len(prices)
    reliable = sample_count >= MIN_RELIABLE_SAMPLE

    region_average = round(statistics.mean(prices), 0) if prices else None
    region_median = round(statistics.median(prices), 0) if prices else None

    savings_amount = None
    savings_rate = None
    if reliable and region_median is not None:
        savings_amount = max(region_median - float(menu_item.price), 0.0)
        savings_rate = (
            round(savings_amount / region_median * 100, 1) if region_median > 0 else 0.0
        )

    return MenuPriceComparison(
        menu_item_id=menu_item.id,
        name=menu_item.name,
        store_price=float(menu_item.price),
        place_id=menu_item.place_id,
        region_average=region_average,
        region_median=region_median,
        sample_count=sample_count,
        savings_amount=savings_amount,
        savings_rate=savings_rate,
        reliable=reliable,
    )


async def best_expected_savings(
    session: AsyncSession, menu_items: list[MenuItem], lat: float, lng: float
) -> float:
    """매장의 메뉴 중 신뢰 가능한 비교 데이터가 있는 항목 중 가장 큰 절약액.
    비교 가능한 메뉴가 없으면 0 (방문 XP를 지어내지 않기 위함)."""
    best = 0.0
    for item in menu_items:
        cmp = await compare_menu_item(session, item, lat, lng)
        if cmp.savings_amount and cmp.savings_amount > best:
            best = cmp.savings_amount
    return best
