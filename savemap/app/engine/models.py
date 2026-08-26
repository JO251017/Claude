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
    # 절약액이 무엇과 비교해 나온 값인지("region"/"gov"/"ai"/None) — Offer에서 그대로
    # 가져온다. AI 절약 리포트가 "실측 데이터 반영"을 AI 추정과 섞어서 말하지 않도록
    # 검색 응답까지 그대로 들고 간다.
    benchmark_source: str | None = None
    # 계산 당시 이웃 매장 표본 수(region 기준일 때만 의미 있음) — 신뢰도 등급이
    # "표본 2곳"과 "표본 30곳"을 구분하는 데 쓴다. 재동기화 전 구 데이터는 None.
    benchmark_sample_count: int | None = None
    place_category_name: str | None = None
    place_kakao_id: str | None = None
    # 전국지역화폐가맹점표준데이터와 매칭돼 검증된 매장인지 — 가격/할인 계산과는
    # 무관하다(이 데이터엔 금액이 없다). 검색 결과에 정보성 배지로만 노출된다.
    accepts_local_currency: bool = False
