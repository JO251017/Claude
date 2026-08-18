from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import Category, Layer


class MerchantVerificationGrant(BaseModel):
    """관리자가 특정 사용자에게 사업자 인증을 부여할 때 쓰는 요청 바디(2-3, 2026-08-13)."""

    user_id: str
    note: str | None = None


class MerchantVerificationResponse(BaseModel):
    user_id: str
    note: str | None = None
    verified_at: datetime


class PlaceCreate(BaseModel):
    name: str
    address: str | None = None
    lat: float
    lng: float
    phone: str | None = None
    kakao_place_id: str | None = None


class PlaceResponse(BaseModel):
    id: int
    name: str
    address: str | None = None
    phone: str | None = None


class OfferCreate(BaseModel):
    place_id: int
    title: str
    category: Category
    base_price: float | None = None
    store_discount: float | None = None
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    ttl_sec: int | None = None


class OfferUpdate(BaseModel):
    title: str | None = None
    base_price: float | None = None
    store_discount: float | None = None
    expires_at: datetime | None = None
    ttl_sec: int | None = None


class OfferResponse(BaseModel):
    id: int
    place_id: int
    title: str
    category: Category
    layer: Layer
    base_price: float | None = None
    store_discount: float | None = None
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    ttl_sec: int | None = None


class MenuItemCreate(BaseModel):
    place_id: int
    name: str
    price: float
    source_url: str | None = None


class MenuItemUpdate(BaseModel):
    price: float | None = None
    source_url: str | None = None


class MenuItemResponse(BaseModel):
    id: int
    place_id: int
    name: str
    price: float
    source_url: str | None = None
    verified_at: datetime | None = None
    # 이 가격이 무엇과 비교돼 지도에 절약 정보로 떴는지 사장님에게 그 자리에서 알려주기 위함
    region_median: float | None = None
    sample_count: int = 0
    savings_amount: float | None = None
    savings_rate: float | None = None
    reliable: bool = False
    benchmark_source: str | None = None
    benchmark_price: float | None = None
    listed_on_map: bool = False
    # 커뮤니티 메뉴 제보 경로에서만 0보다 클 수 있다 (새 메뉴 정보를 더했을 때 보상)
    xp_awarded: int = 0
    # 이번 제보 항목이 실제로 어떻게 처리됐는지(2026-08-18, 항목 단위 갱신 도입) —
    # "created"(새 메뉴로 등록) / "unchanged"(기존과 같은 가격이라 그대로 둠) /
    # "updated"(AI 검토 통과, 가격 갱신) / "rejected"(AI 검토 거부, 기존 가격 유지).
    # 사업자 콘솔(항상 "created"/직접 수정) 경로에선 그대로 "created"만 쓴다.
    status: str = "created"
    # updated/rejected일 때 AI가 판단한 한 줄 이유. created/unchanged면 None.
    review_note: str | None = None


class MenuItemGuessItem(BaseModel):
    name: str
    price: float


class MenuItemAnalyzeResponse(BaseModel):
    image_url: str
    items: list[MenuItemGuessItem]
