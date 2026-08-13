from pydantic import BaseModel, Field

from app.domain.enums import BusinessStatus


class MenuPriceComparisonResponse(BaseModel):
    menu_item_id: int
    name: str
    store_price: float
    region_average: float | None = None
    region_median: float | None = None
    sample_count: int
    savings_amount: float | None = None
    savings_rate: float | None = None
    reliable: bool
    benchmark_source: str | None = None
    benchmark_price: float | None = None


class MenuReportItem(BaseModel):
    name: str
    price: float
    source_url: str | None = None


class MenuReportBatchCreate(BaseModel):
    """아직 가격 정보가 없는 매장의 메뉴를 아무 사용자나 실제 사진으로 제보할 때 쓴다.
    place_id가 있으면(=이미 SaveMap DB에 Place가 있는 경우, 예: 인허가 데이터로 미리
    깔아둔 매장) 그 Place에 바로 붙이고, 없으면 kakao_place_id로 찾거나(카카오로만
    발견된 매장) 그마저 없으면 새로 만든다.

    한 장의 메뉴판 사진에서 메뉴 여러 개가 한 번에 인식되는 게 정상 흐름이라
    배치(items)로 받는다 — "이미 등록된 매장" 판정(2026-08-13, PlaceMenuAlreadyRegisteredError)
    도 이 배치 전체에 대해 한 번만 적용돼서, 같은 사진에서 나온 여러 메뉴를 한 번에
    제보하는 정상 케이스가 걸리지 않는다."""

    place_id: int | None = None
    kakao_place_id: str | None = None
    place_name: str
    address: str | None = None
    phone: str | None = None
    category_name: str | None = None
    lat: float
    lng: float
    items: list[MenuReportItem] = Field(min_length=1)


class StatusUpdateCreate(BaseModel):
    status: BusinessStatus
    lat: float
    lng: float
    accuracy_m: float | None = None


class RecommendationResponse(BaseModel):
    place_id: int
    is_new: bool
    recommend_count: int


class StatusUpdateResponse(BaseModel):
    place_id: int
    status: BusinessStatus
    distance_m: float
    is_new_interest: bool
    interest_count: int
    xp_awarded: int
