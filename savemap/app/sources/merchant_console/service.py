from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Layer, SourceType
from app.ingestion.normalize import NormalizedOffer
from app.ingestion.upsert import upsert_offers
from app.ingestion.validate import validate
from app.sources.merchant_console.ttl import set_flash_ttl


async def register_offer(session: AsyncSession, payload: NormalizedOffer) -> int:
    payload.source = SourceType.S3_MERCHANT
    validate(payload)
    count = await upsert_offers(session, [payload])
    return count


async def register_flash_offer(
    session: AsyncSession, payload: NormalizedOffer, offer_id: int, ttl_sec: int
) -> None:
    payload.layer = Layer.FLASH
    payload.ttl_sec = ttl_sec
    validate(payload)
    await set_flash_ttl(offer_id, ttl_sec)
