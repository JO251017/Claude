from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import Category, Layer


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


class MenuItemGuessItem(BaseModel):
    name: str
    price: float


class MenuItemAnalyzeResponse(BaseModel):
    image_url: str
    items: list[MenuItemGuessItem]
