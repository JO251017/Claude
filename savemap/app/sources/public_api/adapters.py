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
    """data.go.kr: 전국주차장정보표준데이터 (한국지능정보사회진흥원) — 승인됨"""

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("전국주차장정보표준데이터 요청 URL/응답 필드 확인 후 구현 (미확인)")


class SportsFacilityAdapter(PublicApiAdapter):
    """data.go.kr: 전국체육시설 정보 (서울올림픽기념국민체육진흥공단) — 승인됨"""

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("전국체육시설 정보 요청 URL/응답 필드 확인 후 구현 (미확인)")


class CultureFacilityAdapter(PublicApiAdapter):
    """data.go.kr: 한국문화정보원_문화시설조회서비스 — 승인됨"""

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("문화시설조회서비스 요청 URL/응답 필드 확인 후 구현 (미확인)")


class CultureFestivalAdapter(PublicApiAdapter):
    """data.go.kr: 전국문화축제표준데이터 (한국지능정보사회진흥원) — 승인됨"""

    layer = Layer.REGULAR

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("전국문화축제표준데이터 요청 URL/응답 필드 확인 후 구현 (미확인)")


class MarketAreaInfoAdapter(PublicApiAdapter):
    """data.go.kr: 소상공인시장진흥공단_상가(상권)정보_API — 승인됨"""

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("상가(상권)정보 API 요청 URL/응답 필드 확인 후 구현 (미확인)")


class OnnuriMerchantAdapter(PublicApiAdapter):
    """data.go.kr: 소상공인시장진흥공단_전국 온누리상품권 가맹점 현황 — 승인됨"""

    layer = Layer.REGULAR

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("온누리상품권 가맹점 현황 요청 URL/응답 필드 확인 후 구현 (미확인)")


class LocalCurrencyMerchantAdapter(PublicApiAdapter):
    """data.go.kr: 한국조폐공사_지역사랑상품권_가맹점_업종별_결제정보 — 승인됨"""

    layer = Layer.REGULAR

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("지역사랑상품권 가맹점 결제정보 요청 URL/응답 필드 확인 후 구현 (미확인)")


class TourApiAdapter(PublicApiAdapter):
    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("TourAPI 엔드포인트/필드 확인 후 구현 (미확인)")


class OpinetAdapter(PublicApiAdapter):
    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("오피넷 API 엔드포인트/필드 확인 후 구현 (미확인)")


ADAPTERS: list[type[PublicApiAdapter]] = [
    PublicParkingAdapter,
    SportsFacilityAdapter,
    CultureFacilityAdapter,
    CultureFestivalAdapter,
    MarketAreaInfoAdapter,
    OnnuriMerchantAdapter,
    LocalCurrencyMerchantAdapter,
    TourApiAdapter,
    OpinetAdapter,
]
