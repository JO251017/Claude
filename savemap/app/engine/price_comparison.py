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

# 이 개수(=이웃 매장 수, 비교 대상 매장 자신은 빼고 센다) 미만이면 평균/중앙값을
# 신뢰할 수 없다고 보고 "비교 데이터 부족"으로 표시한다(기획서 §5). 사용자 지시로
# 이웃 2곳까지는 비교 가능하다고 판단.
MIN_RELIABLE_SAMPLE = 2

# 실측 비교 반경 사다리(2026-09-04). 가까운 곳부터 보고, 표본이 모자랄 때만
# 넓힌다 — 무조건 넓게 잡으면 커버리지는 늘지만 "주변 시세"라는 말이 무의미해진다
# (10km 밖 매장 가격과 비교해놓고 "주변보다 싸다"고 하면 사실과 다르다).
#
# 운영 DB 무작위 400건 표본 실측: 3km에서 31.0%, 10km까지 넓히면 43.3%가 비교
# 가능했다. 가까운 표본이 있으면 그걸 쓰고, 없을 때만 10km를 쓰되 실제로 쓴
# 반경을 결과에 남겨서(benchmark_radius_km) 화면 문구가 "주변"인지 "같은 지역"인지
# 정직하게 갈리게 한다.
BENCHMARK_RADIUS_LADDER_KM = (3.0, 10.0)
# 이 값을 넘는 반경으로 잡힌 비교는 "주변"이라 부르지 않는다.
NEARBY_RADIUS_MAX_KM = 3.0


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
    # "region" 기준일 때 실제로 표본을 모은 반경(km). 3km 안에서 표본이 모자라
    # 넓혀 잡았으면 그 사실을 화면 문구까지 그대로 전달한다 — 먼 곳 가격과
    # 비교해놓고 "주변"이라고 말하지 않기 위해서다.
    benchmark_radius_km: float | None = None


def _region_prices_stmt(name: str, lat: float, lng: float, radius_km: float, exclude_place_id: int | None):
    """쿼리 생성만 순수 함수로 뺐다 — 샌드박스에 DB가 없어서, 자기표본 제외 조건이
    실제로 SQL에 들어가는지 검증할 수 있는 유일한 지점이 컴파일된 문자열이다."""
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
    if exclude_place_id is not None:
        stmt = stmt.where(MenuItem.place_id != exclude_place_id)
    return stmt


async def _region_prices(
    session: AsyncSession,
    name: str,
    lat: float,
    lng: float,
    radius_km: float,
    *,
    exclude_place_id: int | None = None,
) -> list[float]:
    """주변 반경에서 같은 메뉴를 파는 "다른" 매장들의 실제 등록가.

    예전엔 메뉴명이 글자 하나까지 같아야 매칭돼서, "아메리카노"와 "아메리카노(ICE)"가
    서로 다른 메뉴로 갈렸다 — 실제 가격이 12,000건 넘게 있는데도 비교가 안 돼서
    대부분 AI 추정 통상가로 떨어지던 원인이다. 정규화된 이름으로 매칭한다.

    exclude_place_id: 비교 대상 매장 자신을 표본에서 뺀다(2026-08-22 수정 — 원래
    빠져 있지 않아서, 매장 자신은 항상 반경 0에 있으니 표본에 항상 포함됐다. 그러면
    MIN_RELIABLE_SAMPLE=2가 실제론 "이웃 1곳"만 있어도 만족됐고, 표본이 정확히
    2건(자기+이웃1)이면 median이 (내가격+이웃가격)/2가 돼서 실제 가격차의 절반만
    절약으로 계산되는 버그가 있었다). menu_item_id가 아니라 place_id로 빼는 이유는,
    한 매장이 같은 메뉴를 표기만 다르게(예: "아메리카노"/"아메리카노(ICE)") 여러 행
    등록해도 전부 같은 normalized_name으로 묶이기 때문 — id로만 빼면 자기 매장의
    다른 행이 표본에 남아 편향이 재발한다."""
    stmt = _region_prices_stmt(name, lat, lng, radius_km, exclude_place_id)
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
    session: AsyncSession, menu_item: MenuItem, lat: float, lng: float, radius_km: float | None = None
) -> MenuPriceComparison:
    """radius_km를 주면 그 반경 하나만 본다(호출부가 명시적으로 정한 경우).
    안 주면 BENCHMARK_RADIUS_LADDER_KM를 가까운 순서로 올라가며, 표본이
    MIN_RELIABLE_SAMPLE에 도달하는 첫 반경에서 멈춘다."""
    ladder = (radius_km,) if radius_km is not None else BENCHMARK_RADIUS_LADDER_KM
    prices: list[float] = []
    used_radius_km = ladder[0]
    for candidate_radius in ladder:
        prices = await _region_prices(
            session, menu_item.name, lat, lng, candidate_radius, exclude_place_id=menu_item.place_id
        )
        used_radius_km = candidate_radius
        if len(prices) >= MIN_RELIABLE_SAMPLE:
            break
    sample_count = len(prices)
    reliable = sample_count >= MIN_RELIABLE_SAMPLE

    region_average = round(statistics.mean(prices), 0) if prices else None
    region_median = round(statistics.median(prices), 0) if prices else None

    # 비교 기준 사다리: 주변 실측 > 정부 통계(참가격 외식비) > AI 추정.
    # 근거가 강한 쪽을 항상 먼저 쓴다. 다만 이 함수가 다시 불릴 때만 사다리가
    # 재평가된다 — 주변 매장이 나중에 등록돼도 "자동 승격"은 아니고, 이미 만들어진
    # 오퍼는 재동기화 배치(app/engine/offer_resync.py)가 돌 때 승격된다.
    benchmark_source = None
    benchmark_price = None
    benchmark_period = None
    benchmark_radius_km = None
    if reliable and region_median is not None:
        benchmark_source, benchmark_price = "region", float(region_median)
        benchmark_radius_km = used_radius_km
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
        benchmark_radius_km=benchmark_radius_km,
    )
