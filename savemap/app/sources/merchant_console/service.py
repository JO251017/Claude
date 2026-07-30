from datetime import datetime, timezone

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MenuItemNotFoundError, OfferNotFoundError, PlaceNotFoundError
from app.core.spatial import ewkt_point, to_h3
from app.domain.enums import Category, Layer, SourceType
from app.domain.menu_item import MenuItem
from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.price_comparison import compare_menu_item
from app.sources.merchant_console.ttl import clear_flash_ttl, set_flash_ttl


async def create_place(
    session: AsyncSession,
    owner_user_id: str,
    name: str,
    address: str | None,
    lat: float,
    lng: float,
) -> Place:
    place = Place(
        name=name,
        address=address,
        owner_user_id=owner_user_id,
        geom=ewkt_point(lat, lng),
        h3_r9=to_h3(lat, lng),
    )
    session.add(place)
    await session.commit()
    await session.refresh(place)
    return place


async def list_places(session: AsyncSession, owner_user_id: str) -> list[Place]:
    stmt = select(Place).where(Place.owner_user_id == owner_user_id).order_by(Place.id)
    return list((await session.execute(stmt)).scalars().all())


async def _get_owned_place(session: AsyncSession, owner_user_id: str, place_id: int) -> Place:
    place = await session.get(Place, place_id)
    if place is None or place.owner_user_id != owner_user_id:
        raise PlaceNotFoundError()
    return place


async def _get_owned_offer(session: AsyncSession, owner_user_id: str, offer_id: int) -> Offer:
    offer = await session.get(Offer, offer_id)
    if offer is None:
        raise OfferNotFoundError()
    place = await session.get(Place, offer.place_id)
    if place is None or place.owner_user_id != owner_user_id:
        raise OfferNotFoundError()
    return offer


async def create_offer(
    session: AsyncSession,
    owner_user_id: str,
    place_id: int,
    title: str,
    category: Category,
    base_price: float | None = None,
    store_discount: float | None = None,
    valid_from: datetime | None = None,
    expires_at: datetime | None = None,
    ttl_sec: int | None = None,
) -> Offer:
    await _get_owned_place(session, owner_user_id, place_id)

    layer = Layer.FLASH if ttl_sec is not None else Layer.REGULAR
    offer = Offer(
        place_id=place_id,
        source=SourceType.S3_MERCHANT,
        layer=layer,
        category=category,
        title=title,
        base_price=base_price,
        store_discount=store_discount,
        valid_from=valid_from,
        expires_at=expires_at,
        ttl_sec=ttl_sec,
    )
    session.add(offer)
    await session.commit()
    await session.refresh(offer)

    if layer == Layer.FLASH:
        await set_flash_ttl(offer.id, ttl_sec)

    return offer


async def list_offers(session: AsyncSession, owner_user_id: str) -> list[Offer]:
    stmt = (
        select(Offer)
        .join(Place, Offer.place_id == Place.id)
        .where(Place.owner_user_id == owner_user_id)
        .order_by(Offer.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_offer(session: AsyncSession, owner_user_id: str, offer_id: int) -> Offer:
    return await _get_owned_offer(session, owner_user_id, offer_id)


async def update_offer(
    session: AsyncSession,
    owner_user_id: str,
    offer_id: int,
    title: str | None = None,
    base_price: float | None = None,
    store_discount: float | None = None,
    expires_at: datetime | None = None,
    ttl_sec: int | None = None,
) -> Offer:
    offer = await _get_owned_offer(session, owner_user_id, offer_id)

    if title is not None:
        offer.title = title
    if base_price is not None:
        offer.base_price = base_price
    if store_discount is not None:
        offer.store_discount = store_discount
    if expires_at is not None:
        offer.expires_at = expires_at
    if ttl_sec is not None:
        offer.ttl_sec = ttl_sec
        offer.layer = Layer.FLASH
        await set_flash_ttl(offer.id, ttl_sec)

    await session.commit()
    await session.refresh(offer)
    return offer


async def delete_offer(session: AsyncSession, owner_user_id: str, offer_id: int) -> None:
    offer = await _get_owned_offer(session, owner_user_id, offer_id)
    if offer.layer == Layer.FLASH:
        await clear_flash_ttl(offer.id)
    await session.delete(offer)
    await session.commit()


async def _get_owned_menu_item(session: AsyncSession, owner_user_id: str, menu_item_id: int) -> MenuItem:
    item = await session.get(MenuItem, menu_item_id)
    if item is None:
        raise MenuItemNotFoundError()
    place = await session.get(Place, item.place_id)
    if place is None or place.owner_user_id != owner_user_id:
        raise MenuItemNotFoundError()
    return item


async def _sync_menu_offer(session: AsyncSession, place: Place, item: MenuItem) -> None:
    """메뉴가 지역 평균보다 확실히 싸면(비교 데이터 신뢰 가능) 지도 검색에 뜨도록 오퍼를
    자동 생성/갱신한다. 더 이상 싸지 않게 되면 오퍼를 지운다 — 지도 검색(/v1/search)이
    offer 테이블만 보는 구조라, 메뉴만 등록하고 오퍼가 없으면 지도에 전혀 안 뜨는 문제를
    해결하기 위함. menu_item_id로 추적해 중복 생성하지 않는다."""
    point = to_shape(place.geom)
    cmp = await compare_menu_item(session, item, point.y, point.x)

    existing_offer = (
        await session.execute(select(Offer).where(Offer.menu_item_id == item.id))
    ).scalar_one_or_none()

    if cmp.reliable and cmp.savings_amount and cmp.savings_amount > 0:
        title = f"{item.name} {round(item.price):,}원 · 지역 평균보다 저렴"
        if existing_offer is None:
            session.add(
                Offer(
                    place_id=place.id,
                    source=SourceType.S3_MERCHANT,
                    layer=Layer.CORE_BASE,
                    category=Category.DISCOUNT,
                    title=title,
                    base_price=cmp.region_median,
                    store_discount=cmp.savings_amount,
                    menu_item_id=item.id,
                )
            )
        else:
            existing_offer.title = title
            existing_offer.base_price = cmp.region_median
            existing_offer.store_discount = cmp.savings_amount
    elif existing_offer is not None:
        await session.delete(existing_offer)

    await session.commit()


async def create_menu_item(
    session: AsyncSession,
    owner_user_id: str,
    place_id: int,
    name: str,
    price: float,
    source_url: str | None = None,
) -> MenuItem:
    place = await _get_owned_place(session, owner_user_id, place_id)
    item = MenuItem(
        place_id=place_id,
        name=name,
        price=price,
        source=SourceType.S3_MERCHANT,
        source_url=source_url,
        verified_at=datetime.now(timezone.utc),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    await _sync_menu_offer(session, place, item)
    return item


async def list_menu_items_for_owner(session: AsyncSession, owner_user_id: str, place_id: int) -> list[MenuItem]:
    await _get_owned_place(session, owner_user_id, place_id)
    stmt = select(MenuItem).where(MenuItem.place_id == place_id).order_by(MenuItem.id.desc())
    return list((await session.execute(stmt)).scalars().all())


async def update_menu_item(
    session: AsyncSession,
    owner_user_id: str,
    menu_item_id: int,
    price: float | None = None,
    source_url: str | None = None,
) -> MenuItem:
    item = await _get_owned_menu_item(session, owner_user_id, menu_item_id)
    price_changed = price is not None and float(price) != float(item.price)
    if price is not None:
        item.price = price
        item.verified_at = datetime.now(timezone.utc)
    if source_url is not None:
        item.source_url = source_url
    await session.commit()
    await session.refresh(item)

    if price_changed:
        place = await session.get(Place, item.place_id)
        await _sync_menu_offer(session, place, item)
    return item


async def delete_menu_item(session: AsyncSession, owner_user_id: str, menu_item_id: int) -> None:
    item = await _get_owned_menu_item(session, owner_user_id, menu_item_id)
    await session.delete(item)
    await session.commit()
