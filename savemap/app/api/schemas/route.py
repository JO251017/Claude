from pydantic import BaseModel, Field

from app.api.schemas.search import SearchResultItem
from app.domain.enums import Category, PaymentMethodType


class RouteSuggestRequest(BaseModel):
    lat: float
    lng: float
    budget: float = Field(gt=0)
    party_size: int = Field(default=1, ge=1, le=20)
    radius_km: float | None = None
    category: Category | None = None
    payment_methods: list[PaymentMethodType] = Field(default_factory=list)


class RouteStopItem(SearchResultItem):
    """SearchResultItem과 완전히 같은 모양 + 코스 내 순서 하나만 추가 — 프론트가 새
    상세뷰를 만들 필요 없이 기존 오퍼 상세 열기 로직을 그대로 재사용하게 한다."""

    order: int


class RouteSuggestResponse(BaseModel):
    fits_budget: bool
    budget: float
    party_size: int
    radius_km: float
    stop_count: int
    total_spend: float
    total_savings: float
    remaining_budget: float
    stops: list[RouteStopItem]
    summary: str
    # "ai"=Gemini가 작성한 문장, "template"=결정론적 기본 문장(Gemini 미설정/실패,
    # 또는 코스가 비어 지어낼 게 없는 경우). 프론트가 출처를 그대로 보여줄 수 있다.
    summary_source: str
