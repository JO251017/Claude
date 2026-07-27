import asyncio

from app.core.db import SessionLocal
from app.core.errors import OfferNotFoundError, PlaceNotFoundError
from app.domain.enums import Category
from app.sources.merchant_console import service


async def main():
    async with SessionLocal() as session:
        place = await service.create_place(session, "user_A", "유저A 가게", None, 36.99, 127.11)
        print("place owner=user_A id=", place.id)

    async with SessionLocal() as session:
        try:
            await service.create_offer(
                session, "user_B", place.id, "남의 가게에 혜택 등록 시도", Category.DISCOUNT
            )
            raise AssertionError("should have raised PlaceNotFoundError")
        except PlaceNotFoundError:
            print("OK: user_B blocked from creating offer on user_A place")

    async with SessionLocal() as session:
        offer = await service.create_offer(
            session,
            "user_A",
            place.id,
            "user_A 혜택",
            Category.DISCOUNT,
            base_price=5000,
            store_discount=1000,
        )
        print("offer created by user_A id=", offer.id)

    async with SessionLocal() as session:
        try:
            await service.get_offer(session, "user_B", offer.id)
            raise AssertionError("should have raised OfferNotFoundError")
        except OfferNotFoundError:
            print("OK: user_B blocked from reading user_A offer")

    async with SessionLocal() as session:
        try:
            await service.delete_offer(session, "user_B", offer.id)
            raise AssertionError("should have raised OfferNotFoundError")
        except OfferNotFoundError:
            print("OK: user_B blocked from deleting user_A offer")

    async with SessionLocal() as session:
        got = await service.get_offer(session, "user_A", offer.id)
        print("OK: user_A can still read own offer:", got.title)


if __name__ == "__main__":
    asyncio.run(main())
