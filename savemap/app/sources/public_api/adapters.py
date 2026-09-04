import asyncio
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.domain.enums import Layer, SourceType
from app.ingestion.normalize import NormalizedOffer, normalize
from app.integrations.gov_data import GovDataClient
from app.integrations.kakao import KakaoClient


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
        # 전국 데이터 중 앞부분만 가져오면 지역이 한쪽으로 쏠려 특정 지역 근처 검색에 거의
        # 안 잡힐 수 있어(예: 서비스 지역이 다른 도시면 결과가 0에 가까움), 최대한 넓게 가져온다.
        data = await client.fetch(PARKING_PATH, {"pageNo": 1, "numOfRows": 1000, "type": "json"})

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


def _map_sports_item(item: dict) -> dict | None:
    """사용자가 제공한 실제 응답 예시(XML)로 필드명이 확인됨. 공공/민간 구분 없이 전부
    포함한다(사용자 지시) — 다만 이 데이터셋엔 무료/할인 여부 필드가 없어(민간 사설
    헬스장도 섞여 있음) 특정 혜택을 보장하는 카테고리(무료/할인) 대신 "지역혜택"(주변
    체육시설 정보)으로 분류해 허위 할인 정보처럼 보이지 않게 한다. 폐업/휴업은 제외한다."""
    if item.get("faci_stat_nm") != "정상운영":
        return None
    name = item.get("faci_nm")
    lat = _to_float(item.get("faci_lat"))
    lng = _to_float(item.get("faci_lot"))
    if not name or lat is None or lng is None:
        return None

    ftype = item.get("ftype_nm")
    return {
        "place_name": name,
        "title": f"{name}{f' ({ftype})' if ftype else ''}",
        "category": "지역혜택",
        "lat": lat,
        "lng": lng,
        "address": item.get("faci_road_addr") or item.get("faci_addr"),
        "external_ref": item.get("faci_cd"),
        "extra": {
            "facility_type": ftype,
            "business_type": item.get("fcob_nm"),
            "phone": item.get("faci_tel_no"),
            "region": item.get("cp_nm"),
            "district": item.get("addr_cpb_nm") or item.get("cpb_nm"),
        },
    }


class SportsFacilityAdapter(PublicApiAdapter):
    """data.go.kr: 전국체육시설 정보 (서울올림픽기념국민체육진흥공단) — 승인됨,
    응답 필드 확인됨 (사용자 제공 실제 응답 예시 기준). XML 응답이라 JSON 계열
    GovDataClient 대신 직접 XML을 파싱한다.

    End Point: https://apis.data.go.kr/B551014/SRVC_API_SFMS_FACI (사용자 제공, 확인됨)
    """

    async def fetch_raw(self) -> list[dict]:
        async with httpx.AsyncClient(base_url=SPORTS_BASE_URL, timeout=30) as client:
            resp = await client.get(
                SPORTS_PATH,
                params={"serviceKey": settings.data_go_kr_key, "pageNo": 1, "numOfRows": 100},
            )
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        mapped = [
            _map_sports_item({child.tag: (child.text or "").strip() for child in item})
            for item in root.findall(".//item")
        ]
        return [m for m in mapped if m is not None]


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
# 2025-07-31 최신본 (사용자가 제공한 Swagger 문서로 경로·필드 모두 확인됨)
ONNURI_PATH = "/api/3060079/v1/uddi:7ffa42f8-01d1-4329-aa94-aefb67c53cf1"


def _map_onnuri_row(row: dict) -> dict | None:
    """odcloud data[] 항목 하나를 파싱한다 (필드명은 사용자 제공 Swagger로 확인됨).
    이 API 자체엔 위도/경도가 없어(소재지 주소 텍스트만 제공) 좌표는 채우지 않는다 —
    어댑터가 이 결과에 카카오 지오코딩으로 좌표를 별도로 채워 넣는다."""
    name = row.get("가맹점명")
    address = row.get("소재지")
    if not name or not address:
        return None
    market_name = row.get("소속 시장명(또는 상점가)")
    return {
        "place_name": name,
        "title": f"온누리상품권 가맹점{f' ({market_name})' if market_name else ''}",
        "category": "지역혜택",
        "address": address,
        "extra": {
            "items": row.get("취급품목"),
            "paper_voucher": row.get("지류형 가맹 여부"),
            "digital_voucher": row.get("디지털형 가맹 여부"),
            "registered_year": row.get("등록년도"),
        },
    }


class OnnuriMerchantAdapter(PublicApiAdapter):
    """data.go.kr(odcloud): 소상공인시장진흥공단_전국 온누리상품권 가맹점 현황 — 승인됨,
    응답 필드 확인됨 (사용자 제공 Swagger 문서 기준, 2025-07-31 최신본).

    End Point: https://api.odcloud.kr/api/3060079/v1/uddi:7ffa42f8-01d1-4329-aa94-aefb67c53cf1
    원본 데이터에 좌표가 없어 매장마다 카카오 주소 검색(geocode)으로 좌표를 채운다
    (동시 처리) — 전국 단위라 항목이 매우 많을 수 있어 한 번에 가져오는 개수를
    max_items로 제한한다.
    주소 지오코딩에 실패한 항목은 (좌표 없이 지도에 표시할 수 없으므로) 건너뛴다.
    "지역혜택 상시 정보"라 만료일이 없는 CORE_BASE 레이어로 분류한다.
    """

    layer = Layer.CORE_BASE

    def __init__(self, kakao: KakaoClient | None = None, max_items: int = 30):
        self.kakao = kakao or KakaoClient()
        self.max_items = max_items

    async def _geocode(self, mapped: dict) -> dict | None:
        try:
            geo = await self.kakao.geocode(mapped["address"])
        except Exception:
            return None
        if geo is None:
            return None
        mapped["lat"] = geo.lat
        mapped["lng"] = geo.lng
        return mapped

    async def fetch_raw(self) -> list[dict]:
        async with httpx.AsyncClient(base_url=ONNURI_BASE_URL, timeout=30) as client:
            resp = await client.get(
                ONNURI_PATH,
                params={"page": 1, "perPage": self.max_items, "serviceKey": settings.data_go_kr_key},
            )
            resp.raise_for_status()
            payload = resp.json()

        candidates = [m for m in (_map_onnuri_row(row) for row in payload.get("data", [])) if m]
        # 주소를 하나씩 순서대로 지오코딩하면 요청이 많을 때 응답이 느려져 Render 무료
        # 플랜의 요청 타임아웃에 걸릴 수 있어, 동시에 처리한다.
        geocoded = await asyncio.gather(*(self._geocode(m) for m in candidates))
        return [m for m in geocoded if m is not None]


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
