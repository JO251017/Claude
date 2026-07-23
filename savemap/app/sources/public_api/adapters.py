from abc import ABC, abstractmethod

from app.domain.enums import Layer, SourceType
from app.ingestion.normalize import NormalizedOffer, normalize


class PublicApiAdapter(ABC):
    source = SourceType.S1_PUBLIC
    layer = Layer.CORE_BASE

    @abstractmethod
    async def fetch_raw(self) -> list[dict]:
        ...

    async def collect(self) -> list[NormalizedOffer]:
        raw_items = await self.fetch_raw()
        return [normalize(item, self.source, self.layer) for item in raw_items]


class PublicParkingAdapter(PublicApiAdapter):
    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("공공데이터포털 주차장 API 엔드포인트/필드 확인 후 구현 (미확인)")


class TourApiAdapter(PublicApiAdapter):
    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("TourAPI 엔드포인트/필드 확인 후 구현 (미확인)")


class OpinetAdapter(PublicApiAdapter):
    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("오피넷 API 엔드포인트/필드 확인 후 구현 (미확인)")


ADAPTERS: list[type[PublicApiAdapter]] = [
    PublicParkingAdapter,
    TourApiAdapter,
    OpinetAdapter,
]
