from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Category, PaymentMethodType


class SearchResultItem(BaseModel):
    offer_id: int
    place_name: str
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
    score: float


class SearchResponse(BaseModel):
    count: int
    radius_km: float
    results: list[SearchResultItem]


class SearchQuery(BaseModel):
    lat: float
    lng: float
    radius_km: float | None = None
    category: Category | None = None
    payment_methods: list[PaymentMethodType] = Field(default_factory=list)
