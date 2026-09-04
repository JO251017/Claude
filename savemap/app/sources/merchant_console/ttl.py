from app.core.redis import redis_client

FLASH_KEY_PREFIX = "flash:offer:"


def _key(offer_id: int) -> str:
    return f"{FLASH_KEY_PREFIX}{offer_id}"


async def set_flash_ttl(offer_id: int, ttl_sec: int) -> None:
    await redis_client.set(_key(offer_id), "1", ex=ttl_sec)


async def clear_flash_ttl(offer_id: int) -> None:
    await redis_client.delete(_key(offer_id))


async def is_flash_active(offer_id: int) -> bool:
    return await redis_client.exists(_key(offer_id)) == 1
