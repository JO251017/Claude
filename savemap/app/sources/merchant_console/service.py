from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import OfferNotFoundError, PlaceNotFoundError
from app.core.spatial import ewkt_point, to_h3
from app.domain.enums import Category, Layer, SourceType
from app.domain.offer import Offer
from app.domain.place import Place
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
