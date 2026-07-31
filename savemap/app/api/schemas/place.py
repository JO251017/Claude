from pydantic import BaseModel

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


class MenuReportCreate(BaseModel):
    """아직 SaveMap에 등록 안 된(카카오로만 발견된) 매장의 메뉴를 아무 사용자나 실제
    사진으로 제보할 때 쓴다. kakao_place_id로 매장을 찾거나 없으면 새로 만든다."""

    kakao_place_id: str
    place_name: str
    address: str | None = None
    phone: str | None = None
    category_name: str | None = None
    lat: float
    lng: float
    name: str
    price: float
    source_url: str | None = None


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
