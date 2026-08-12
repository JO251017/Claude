from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Category, Layer
from app.domain.menu_item import MenuItem
from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.price_comparison import MenuPriceComparison, compare_menu_item


async def sync_menu_offer(session: AsyncSession, place: Place, item: MenuItem) -> MenuPriceComparison:
    """메뉴 가격이 등록/제보되면(사장님 등록이든 사용자 제보든) 지도 검색에 뜨도록
    오퍼를 항상 생성/갱신한다 — 지도 검색(/v1/search)이 offer 테이블만 보는 구조라,
    메뉴만 있고 오퍼가 없으면 매장이 지도에서 완전히 사라지고(가격 없는 "발견됨"으로도
    못 뜸) "찾아갈 이유"가 안 보이는 문제를 해결하기 위함.
    지역 평균보다 확실히 싸면(비교 데이터 신뢰 가능) 절약률/절약액을 보여주고, 아직
    비교할 실측 데이터가 부족하면 AI 추정 통상가라도 기준으로 삼아 절약을 계산한다
    (실측이 항상 우선, 표본이 쌓이면 자동 승격). 그것도 없으면 지어낸 할인 없이
    등록된 실제 가격 그대로를 보여준다 — 가격 정보 자체가 방문 여부를 판단할
    "찾아갈 이유"다. menu_item_id로 추적해 중복 생성하지 않는다. 비교 결과를 반환해
    등록자에게 "지금 지도에 절약 정보로 떴는지" 그 자리에서 알려줄 수 있게 한다."""
    point = to_shape(place.geom)
    cmp = await compare_menu_item(session, item, point.y, point.x)

    existing_offer = (
        await session.execute(select(Offer).where(Offer.menu_item_id == item.id))
    ).scalar_one_or_none()

    cheaper = bool(cmp.savings_amount and cmp.savings_amount > 0)
    if cheaper:
        label = "지역 평균보다 저렴" if cmp.benchmark_source == "region" else "통상가보다 저렴 (AI 추정)"
        title = f"{item.name} {round(item.price):,}원 · {label}"
        base_price = cmp.benchmark_price
        store_discount = cmp.savings_amount
    else:
        title = f"{item.name} {round(item.price):,}원"
        base_price = float(item.price)
        store_discount = 0.0

    if existing_offer is None:
        session.add(
            Offer(
                place_id=place.id,
                source=item.source,
                layer=Layer.CORE_BASE,
                category=Category.DISCOUNT,
                title=title,
                base_price=base_price,
                store_discount=store_discount,
                benchmark_source=cmp.benchmark_source if cheaper else None,
                menu_item_id=item.id,
            )
        )
    else:
        existing_offer.title = title
        existing_offer.base_price = base_price
        existing_offer.store_discount = store_discount
        existing_offer.benchmark_source = cmp.benchmark_source if cheaper else None

    await session.commit()
    return cmp
