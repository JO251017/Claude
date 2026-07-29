from abc import ABC, abstractmethod
from datetime import datetime, timezone

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


def _first(item: dict, *keys: str):
    """여러 후보 필드명 중 값이 있는 첫 번째를 반환한다 (필드명이 100% 확정되지 않은 어댑터용)."""
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_yyyymmdd(value) -> datetime | None:
    if not value:
        return None
    s = str(value).strip().replace("-", "").replace(".", "")
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), 23, 59, 59, tzinfo=timezone.utc)
    except ValueError:
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


SPORTS_BASE_URL = "https://apis.data.go.kr"
SPORTS_PATH = "/B551014/SRVC_API_SFMS_FACI"


class SportsFacilityAdapter(PublicApiAdapter):
    """data.go.kr: 전국체육시설 정보 (서울올림픽기념국민체육진흥공단) — 승인됨

    End Point: https://apis.data.go.kr/B551014/SRVC_API_SFMS_FACI (사용자 제공, 확인됨)
    응답 필드명은 확인 안 됨 — data.go.kr 상세 페이지가 자동 접근을 차단해 조회하지 못했다.
    """

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("응답 필드 미확인 (엔드포인트는 확인됨: " + SPORTS_PATH + ")")


CULTURE_FACILITY_BASE_URL = "https://apis.data.go.kr"
CULTURE_FACILITY_PATH = "/B553457/nopenapi/rest/cultureartspaces"


class CultureFacilityAdapter(PublicApiAdapter):
    """data.go.kr: 한국문화정보원_문화시설조회서비스 — 승인됨

    End Point: https://apis.data.go.kr/B553457/nopenapi/rest/cultureartspaces (사용자 제공, 확인됨)
    응답 필드명은 확인 안 됨.
    """

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("응답 필드 미확인 (엔드포인트는 확인됨: " + CULTURE_FACILITY_PATH + ")")


FESTIVAL_BASE_URL = "https://api.data.go.kr"
FESTIVAL_PATH = "/openapi/tn_pubr_public_cltur_fstvl_api"


def _map_festival_item(item: dict) -> dict | None:
    """PublicParkingAdapter와 같은 "공공데이터 표준데이터셋" 소속이라 응답 envelope과
    위도/경도/주소 필드명(latitude/longitude/rdnmadr/lnmadr)은 동일 규격을 따른다고 보고
    구현했다. 축제명·시작/종료일자 필드명은 확정되지 않아 흔한 후보를 순서대로 시도하고,
    끝내 못 찾으면 그 항목은 지어내지 않고 건너뛴다(0건이 나오더라도 허위 데이터보다 낫다)."""
    name = _first(item, "fstvlNm", "festivalNm", "fstvlName")
    lat = _to_float(_first(item, "latitude", "la", "wgs84Lat"))
    lng = _to_float(_first(item, "longitude", "lo", "wgs84Logt"))
    expires_at = _parse_yyyymmdd(_first(item, "fstvlEndDate", "endDate", "fstvlEndDe"))
    if not name or lat is None or lng is None or expires_at is None:
        return None

    return {
        "place_name": name,
        "title": f"{name} (지역축제)",
        "category": "지역혜택",
        "lat": lat,
        "lng": lng,
        "address": _first(item, "rdnmadr", "lnmadr"),
        "external_ref": _first(item, "fstvlId", "festivalId"),
        "valid_from": _parse_yyyymmdd(_first(item, "fstvlStartDate", "startDate", "fstvlBgngDe")),
        "expires_at": expires_at,
        "extra": {
            "host": _first(item, "auspcInsttNm", "hostInsttNm"),
            "phone": _first(item, "phoneNumber", "phoneNumberInfo"),
        },
    }


class CultureFestivalAdapter(PublicApiAdapter):
    """data.go.kr: 전국문화축제표준데이터 (한국지능정보사회진흥원) — 승인됨

    End Point: https://api.data.go.kr/openapi/tn_pubr_public_cltur_fstvl_api (사용자 제공, 확인됨)
    """

    layer = Layer.REGULAR

    async def fetch_raw(self) -> list[dict]:
        client = GovDataClient(base_url=FESTIVAL_BASE_URL)
        data = await client.fetch(FESTIVAL_PATH, {"pageNo": 1, "numOfRows": 100, "type": "json"})

        body = data.get("response", {}).get("body", {})
        items = body.get("items")
        if not items:
            return []
        item_list = items.get("item", []) if isinstance(items, dict) else items
        if isinstance(item_list, dict):
            item_list = [item_list]

        mapped = [_map_festival_item(item) for item in item_list]
        return [m for m in mapped if m is not None]


MARKET_AREA_BASE_URL = "https://apis.data.go.kr"
MARKET_AREA_PATH = "/B553077/api/open/sdsc2"


class MarketAreaInfoAdapter(PublicApiAdapter):
    """data.go.kr: 소상공인시장진흥공단_상가(상권)정보_API — 승인됨

    End Point: https://apis.data.go.kr/B553077/api/open/sdsc2 (사용자 제공, 확인됨)
    응답 필드명은 확인 안 됨. 참고로 이 데이터셋은 일반 상가 목록(가게명·업종·주소)일 뿐
    할인/절약 정보가 없어, 필드를 확인하더라도 SaveMap의 "절약 정보"로 그대로 쓰기는
    적합하지 않다 — 지역화폐/온누리상품권 가맹점 어댑터가 우선순위가 더 높다.
    """

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("응답 필드 미확인 (엔드포인트는 확인됨: " + MARKET_AREA_PATH + ")")


ONNURI_BASE_URL = "https://api.odcloud.kr"
# odcloud 파일데이터형 API는 데이터셋마다 실제 호출 경로에 고유 UDDI 값이 필요한데
# (예: /api/3060079/v1/uddi:xxxxxxxx-....), 그 값은 아직 확인하지 못했다. 지어내지 않는다.
ONNURI_PATH = None


class OnnuriMerchantAdapter(PublicApiAdapter):
    """data.go.kr: 소상공인시장진흥공단_전국 온누리상품권 가맹점 현황 — 승인됨

    End Point: api.odcloud.kr/api (사용자 제공) — odcloud는 파일데이터형 API라 실제 호출 경로가
    데이터셋별 UDDI 값을 포함하는데, 이 값은 아직 확인하지 못했다 (Swagger 문서:
    infuser.odcloud.kr/oas/docs?namespace=3060079/v1). 정확한 경로를 알려주시면 이어서 구현.
    """

    layer = Layer.REGULAR

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("odcloud 데이터셋 경로(UDDI) 미확인 — namespace 3060079")


LOCAL_CURRENCY_BASE_URL = "https://apis.data.go.kr"
LOCAL_CURRENCY_PATH = "/B190001/localGiftsKsciPaymentV1"


class LocalCurrencyMerchantAdapter(PublicApiAdapter):
    """data.go.kr: 한국조폐공사_지역사랑상품권_가맹점_업종별_결제정보 — 승인됨

    End Point: https://apis.data.go.kr/B190001/localGiftsKsciPaymentV1 (사용자 제공, 확인됨)
    응답 필드명은 확인 안 됨.
    """

    layer = Layer.REGULAR

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("응답 필드 미확인 (엔드포인트는 확인됨: " + LOCAL_CURRENCY_PATH + ")")


TOUR_API_BASE_URL = "https://apis.data.go.kr"
TOUR_API_PATH = "/B551011/KorService2"


class TourApiAdapter(PublicApiAdapter):
    """data.go.kr: 한국관광공사_국문 관광정보 서비스 (TourAPI) — 승인됨

    End Point: https://apis.data.go.kr/B551011/KorService2 (사용자 제공, 확인됨)
    구현 보류: 이 API는 일반 관광지 목록(이름/주소/좌표)만 줄 뿐 가격·할인 정보가 없다.
    "절약 정보"로 그대로 노출하면 실제로 무료/할인인지 알 수 없는 곳도 혜택인 것처럼
    보일 수 있어(constraint #14: 허위 데이터 표시 금지), 가격/입장료 필드 확인 전에는
    연결하지 않기로 했다.
    """

    async def fetch_raw(self) -> list[dict]:
        raise NotImplementedError(
            "가격/할인 필드가 없는 API라 절약 정보로 부적합 — 연결 보류 (엔드포인트는 확인됨)"
        )


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
