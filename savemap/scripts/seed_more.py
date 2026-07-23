import asyncio
from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.domain.enums import Category, Layer, SourceType
from app.ingestion.normalize import NormalizedOffer
from app.ingestion.validate import validate
from app.ingestion.upsert import upsert_offers


async def main():
    now = datetime.now(timezone.utc)
    offers = [
        NormalizedOffer(
            source=SourceType.S1_PUBLIC,
            layer=Layer.CORE_BASE,
            category=Category.FREE_PARKING,
            place_name="평택시청 공영주차장",
            title="18시 이후 무료",
            lat=36.9928,
            lng=127.1125,
        ),
        NormalizedOffer(
            source=SourceType.S3_MERCHANT,
            layer=Layer.FLASH,
            category=Category.CLOSING_SOON,
            place_name="평택역 베이커리",
            title="마감 임박 빵 50%",
            lat=36.9920,
            lng=127.1129,
            base_price=8000.0,
            store_discount=4000.0,
            expires_at=now + timedelta(hours=1),
            ttl_sec=3600,
        ),
        NormalizedOffer(
            source=SourceType.S1_PUBLIC,
            layer=Layer.CORE_BASE,
            category=Category.FREE,
            place_name="먼 도서관",
            title="무료 열람실",
            lat=37.5665,
            lng=126.9780,
        ),
    ]
    for o in offers:
        validate(o)
    async with SessionLocal() as session:
        count = await upsert_offers(session, offers)
    print(f"inserted={count}")


asyncio.run(main())
