from abc import ABC, abstractmethod

from app.domain.enums import Layer, SourceType
from app.ingestion.normalize import NormalizedOffer, normalize
from app.integrations.gov_data import GovDataClient


class PublicApiAdapter(ABC):
    source = SourceType.S1_PUBLIC
    layer = Layer.CORE_BASE

    @abstractmethod
    async def fetch_raw(self) -> list[dict]:
        ...

    async def collect(self) -> list[NormalizedOffer]:
        raw_items = await self.fetch_raw()
        return [normalize(item, self.source, self.layer) for item in raw_items]


PARKING_BASE_URL = "https://api.data.go.kr"
PARKING_PATH = "/openapi/tn_pubr_prkplce_info_api"


def _to_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _map_parking_item(item: dict) -> dict:
    """실제 확인된 응답 필드(prkplceNm/latitude/longitude 등)를 normalize() 입력 형태로 변환."""
    return {
        "place_name": item.get("prkplceNm", ""),
        "title": f"{item.get('prkplceNm', '')} 주차장 정보",
        "category": "무료주차",
        "lat": _to_float(item.get("latitude")),
        "lng": _to_float(item.get("longitude")),
        "address": item.get("rdnmadr") or item.get("lnmadr"),
        "external_ref": item.get("prkplceNo"),
        "extra": {
            "operator": item.get("institutionNm"),
            "phone": item.get("phoneNumber"),
            "basic_time": item.get("basicTime"),
            "basic_charge": item.get("basicCharge"),
            "add_unit_time": item.get("addUnitTime"),
            "add_unit_charge": item.get("addUnitCharge"),
            "day_pass_charge": item.get("dayCmmtkt"),
            "month_pass_charge": item.get("monthCmmtkt"),
            "operating_hours": {
                "weekday": [
                    item.get("weekdayOperOpenHhmm"),
                    item.get("weekdayOperColseHhmm"),
                ],
                "saturday": [
                    item.get("satOperOperOpenHhmm"),
                    item.get("satOperCloseHhmm"),
                ],
                "holiday": [
                    item.get("holidayOperOpenHhmm"),
                    item.get("holidayCloseOpenHhmm"),
                ],
            },
            "disabled_parking_zone": item.get("pwdbsPpkZoneYn"),
        },
    }


class PublicParkingAdapter(PublicApiAdapter):
    """data.go.kr: 전국주차장정보표준데이터 (한국지능정보사회진흥원) — 승인됨

    End Point: https://api.data.go.kr/openapi/tn_pubr_prkplce_info_api (실제 확인됨)
    응답 envelope(response.header/body.items 구조)는 data.go.kr 공통 규격을 따른다고 가정 —
    실제 라이브 호출은 이 세션의 네트워크 정책상 불가해 검증 못함 (미확인).
    """

    async def fetch_raw(self) -> list[dict]:
        client = GovDataClient(base_url=PARKING_BASE_URL)
        data = await client.fetch(PARKING_PATH, {"pageNo": 1, "numOfRows": 100, "type": "json"})

        body = data.get("response", {}).get("body", {})
        items = body.get("items")
        if not items:
            return []
        item_list = items.get("item", []) if isinstance(items, dict) else items
        if isinstance(item_list, dict):
            item_list = [item_list]

        return [_map_parking_item(item) for item in item_list]


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
    """data.go.kr: 한국관광공사_국문 관광정보 서비스 (TourAPI) — 승인됨"""

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("TourAPI 요청 URL/응답 필드 확인 후 구현 (미확인)")


class OpinetAdapter(PublicApiAdapter):
    """오피넷(한국석유공사) Open API — 승인됨, 별도 인증키 발급"""

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("오피넷 API 요청 URL/응답 필드 확인 후 구현 (미확인)")


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
