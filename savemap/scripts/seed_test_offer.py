import asyncio
from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.domain.enums import Category, Layer, SourceType
from app.ingestion.normalize import NormalizedOffer
from app.ingestion.validate import validate
from app.ingestion.upsert import upsert_offers


async def main():
    offer = NormalizedOffer(
        source=SourceType.S3_MERCHANT,
        layer=Layer.REGULAR,
        category=Category.DISCOUNT,
        place_name="평택역 A식당",
        title="저녁 타임세일 30%",
        lat=36.9925,
        lng=127.1130,
        address="경기 평택시 평택동",
        base_price=10000.0,
        store_discount=3000.0,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=3),
    )
    validate(offer)
    async with SessionLocal() as session:
        count = await upsert_offers(session, [offer])
    print(f"inserted={count}")


asyncio.run(main())
