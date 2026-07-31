from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Category, PaymentMethodType


class SavingsReportItem(BaseModel):
    """SaveMap의 핵심 콘텐츠. 메뉴가 아니라 "얼마나 절약되고 얼마나 믿을 수 있는지"를
    실제 집계 데이터만으로 계산한 결과 — 데이터가 부족하면 score/grade는 null이고
    confidence_tier가 "low"로 내려간다 (지어내지 않기)."""

    score: int | None = None
    grade: str | None = None
    confidence_tier: str
    confidence_stars: int
    confidence_label: str
    reasons: list[str] = []
    one_line: str = ""


class SignatureMenuItem(BaseModel):
    """대표메뉴 한 줄. 실제 등록된 메뉴 가격(사장님 등록 또는 사진 제보)에서만 나온다 —
    전체 메뉴판은 카카오맵의 역할이고, SaveMap은 절약 계산에 쓰인 대표메뉴 하나만 보여준다."""

    name: str
    price: float


class SearchResultItem(BaseModel):
    offer_id: int
    place_id: int
    place_name: str
    category_name: str | None = None
    business_status: str | None = None
    report: SavingsReportItem | None = None
    signature_menu: SignatureMenuItem | None = None
    recommend_count: int = 0
    kakao_url: str | None = None
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
