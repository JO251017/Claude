from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import Category, Layer


class PlaceCreate(BaseModel):
    name: str
    address: str | None = None
    lat: float
    lng: float


class PlaceResponse(BaseModel):
    id: int
    name: str
    address: str | None = None


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


class MenuItemGuessItem(BaseModel):
    name: str
    price: float


class MenuItemAnalyzeResponse(BaseModel):
    image_url: str
    items: list[MenuItemGuessItem]
