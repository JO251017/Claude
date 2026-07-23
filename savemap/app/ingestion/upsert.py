from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.spatial import ewkt_point, to_h3
from app.domain.offer import Offer
from app.domain.place import Place
from app.ingestion.normalize import NormalizedOffer


async def _get_or_create_place(session: AsyncSession, offer: NormalizedOffer) -> Place:
    stmt = select(Place).where(Place.name == offer.place_name)
    if offer.external_ref:
        stmt = select(Place).where(Place.kakao_place_id == offer.external_ref)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    place = Place(
        name=offer.place_name,
        address=offer.address,
        kakao_place_id=offer.external_ref,
        geom=ewkt_point(offer.lat, offer.lng),
        h3_r9=to_h3(offer.lat, offer.lng),
    )
    session.add(place)
    await session.flush()
    return place


async def upsert_offers(session: AsyncSession, offers: list[NormalizedOffer]) -> int:
    count = 0
    for norm in offers:
        place = await _get_or_create_place(session, norm)
        session.add(
            Offer(
                place_id=place.id,
                source=norm.source,
                layer=norm.layer,
                category=norm.category,
                title=norm.title,
                base_price=norm.base_price,
                store_discount=norm.store_discount,
                valid_from=norm.valid_from,
                expires_at=norm.expires_at,
                ttl_sec=norm.ttl_sec,
            )
        )
        count += 1
    await session.commit()
    return count
