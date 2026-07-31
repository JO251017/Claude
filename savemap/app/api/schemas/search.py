from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Category, PaymentMethodType


class SearchResultItem(BaseModel):
    offer_id: int
    place_id: int
    place_name: str
    # 어떤 메뉴의 가격인지 (예: "아메리카노 3,000원") — 이게 없으면 카드에 금액만 떠서
    # 무슨 음식/음료인지 알 수 없다.
    title: str | None = None
    address: str | None = None
    phone: str | None = None
    category: Category
    distance_m: float
    lat: float
    lng: float
    base_price: float
    final_price: float
    total_savings: float
    savings_rate: float
    expires_at: datetime | None = None
    trust_score: float
    verification_count: int = 0
    last_verified_at: datetime | None = None
    discover_count: int = 0
    dining_count: int = 0
    score: float


class DiscoveredPlaceItem(BaseModel):
    """SaveMap에 아직 가격/절약 정보가 없는, 카카오 로컬 검색으로 발견한 주변 식당·카페.
    콜드스타트 문제(초기에 아무도 매장을 등록 안 했을 때 지도가 텅 비는 것) 완화용."""

    kakao_place_id: str
    place_name: str
    address: str | None = None
    category_name: str | None = None
    phone: str | None = None
    distance_m: float
    lat: float
    lng: float
    kakao_url: str | None = None


class SearchResponse(BaseModel):
    count: int
    radius_km: float
    results: list[SearchResultItem]
    discovered_places: list[DiscoveredPlaceItem] = []


class SearchQuery(BaseModel):
    lat: float
    lng: float
    radius_km: float | None = None
    category: Category | None = None
    payment_methods: list[PaymentMethodType] = Field(default_factory=list)
