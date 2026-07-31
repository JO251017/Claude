from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import Category, Layer, PaymentMethodType


@dataclass
class PaymentBenefit:
    method_type: PaymentMethodType
    rate: float = 0.0
    amount: float = 0.0


@dataclass
class OfferCandidate:
    offer_id: int
    place_id: int
    place_name: str
    category: Category
    layer: Layer
    distance_m: float
    base_price: float
    lat: float
    lng: float
    store_discount: float = 0.0
    payment_benefits: list[PaymentBenefit] = field(default_factory=list)
    expires_at: datetime | None = None
    trust_score: float = 0.5
    verification_count: int = 0
    last_verified_at: datetime | None = None
    place_address: str | None = None
    place_phone: str | None = None
    discover_count: int = 0
    dining_count: int = 0
    recommend_count: int = 0
    title: str | None = None
    menu_item_id: int | None = None
    place_category_name: str | None = None
    place_kakao_id: str | None = None
