import statistics
from dataclasses import dataclass

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.spatial import WGS84_SRID
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.menu_name import canonical_dish, normalize_menu_name
from app.sources.public_api.dine_out_price import get_regional_price, region_from_address

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
    # 절약을 무엇과 비교해 계산했는지:
    #   "region" = 주변 매장 실제 등록가 (가장 신뢰 높음)
    #   "gov"    = 한국소비자원 참가격 외식비 시도별 평균 (정부 조사 통계)
    #   "ai"     = Gemini 추정 통상가 (참고용, 근거가 가장 약함)
    #   None     = 비교 기준 없음
    # 표본이 쌓이면 아래 등급이 자동으로 위 등급으로 승격된다. 사용자에게 항상 이
    # 출처를 같이 보여줘서 추정치를 실측처럼 오해하지 않게 한다.
    benchmark_source: str | None = None
    benchmark_price: float | None = None
    # "gov" 기준일 때 어느 시점 조사분인지 ("2026-07"). 출처를 감춘 채 숫자만
    # 보여주지 않는다는 원칙에 따라 화면까지 그대로 전달한다.
    benchmark_period: str | None = None


async def _region_prices(
    session: AsyncSession, name: str, lat: float, lng: float, radius_km: float
) -> list[float]:
    """주변 반경에서 같은 메뉴를 파는 매장들의 실제 등록가.

    예전엔 메뉴명이 글자 하나까지 같아야 매칭돼서, "아메리카노"와 "아메리카노(ICE)"가
    서로 다른 메뉴로 갈렸다 — 실제 가격이 12,000건 넘게 있는데도 비교가 안 돼서
    대부분 AI 추정 통상가로 떨어지던 원인이다. 정규화된 이름으로 매칭한다."""
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), WGS84_SRID)
    place_geog = cast(Place.geom, Geography)
    point_geog = cast(point, Geography)
    stmt = (
        select(MenuItem.price)
        .join(Place, MenuItem.place_id == Place.id)
        .where(
            MenuItem.normalized_name == normalize_menu_name(name),
            func.ST_DWithin(place_geog, point_geog, radius_km * 1000.0),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [float(r) for r in rows]


async def list_menu_items_by_place(
    session: AsyncSession, place_ids: list[int]
) -> dict[int, list[MenuItem]]:
    """지도 카드 한 장에 그 매장 메뉴 전체가 한눈에 보이도록(검색 결과가 메뉴 하나당
    카드 하나로 쪼개지지 않도록) 매장별 메뉴 목록을 한 번에 가져온다."""
    if not place_ids:
        return {}
    rows = (
        await session.execute(
            select(MenuItem).where(MenuItem.place_id.in_(place_ids)).order_by(MenuItem.id)
        )
    ).scalars().all()
    grouped: dict[int, list[MenuItem]] = {}
    for item in rows:
        grouped.setdefault(item.place_id, []).append(item)
    return grouped


async def _government_stat(session: AsyncSession, menu_item: MenuItem):
    """참가격 외식비 통계에서 이 메뉴에 맞는 시도 평균가를 찾는다.

    품목이 8개뿐이고 시도 단위라 대부분의 메뉴는 여기서 None이 나온다. 매장 주소에서
    시도를 못 읽어내도 None이다 — 엉뚱한 지역 평균과 비교하느니 비교를 안 하는 게 낫다."""
    dish = canonical_dish(menu_item.name)
    if not dish:
        return None
    place = await session.get(Place, menu_item.place_id)
    region = region_from_address(place.address) if place else None
    if not region:
        return None
    return await get_regional_price(session, dish, region)


async def compare_menu_item(
    session: AsyncSession, menu_item: MenuItem, lat: float, lng: float, radius_km: float = 3.0
) -> MenuPriceComparison:
    prices = await _region_prices(session, menu_item.name, lat, lng, radius_km)
    sample_count = len(prices)
    reliable = sample_count >= MIN_RELIABLE_SAMPLE

    region_average = round(statistics.mean(prices), 0) if prices else None
    region_median = round(statistics.median(prices), 0) if prices else None

    # 비교 기준 사다리: 주변 실측 > 정부 통계(참가격 외식비) > AI 추정.
    # 근거가 강한 쪽을 항상 먼저 쓰고, 아래 등급으로는 위가 없을 때만 내려간다 —
    # 주변 매장이 나중에 등록되면 자동으로 실측 기준으로 승격된다.
    benchmark_source = None
    benchmark_price = None
    benchmark_period = None
    if reliable and region_median is not None:
        benchmark_source, benchmark_price = "region", float(region_median)
    else:
        gov_stat = await _government_stat(session, menu_item)
        if gov_stat is not None:
            benchmark_source = "gov"
            benchmark_price = float(gov_stat.price)
            benchmark_period = gov_stat.survey_period
        elif menu_item.ai_typical_price is not None:
            benchmark_source, benchmark_price = "ai", float(menu_item.ai_typical_price)

    savings_amount = None
    savings_rate = None
    if benchmark_price is not None:
        savings_amount = max(benchmark_price - float(menu_item.price), 0.0)
        savings_rate = (
            round(savings_amount / benchmark_price * 100, 1) if benchmark_price > 0 else 0.0
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
        benchmark_source=benchmark_source,
        benchmark_price=benchmark_price,
        benchmark_period=benchmark_period,
    )
