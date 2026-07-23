from dataclasses import dataclass, field

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
    store_discount: float = 0.0
    payment_benefits: list[PaymentBenefit] = field(default_factory=list)
    trust_score: float = 0.5
