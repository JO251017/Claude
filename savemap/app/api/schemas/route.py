from pydantic import BaseModel, Field

from app.api.schemas.search import SearchResultItem
from app.domain.enums import PaymentMethodType, RouteActivity, RoutePreference


class RouteSuggestRequest(BaseModel):
    lat: float
    lng: float
    budget: float = Field(gt=0)
    party_size: int = Field(default=1, ge=1, le=20)
    radius_km: float | None = None
    # "무엇을 할까요?" — 할인/무료/마감세일 같은 절약 수단(Category)이 아니라 사용자가
    # 실제로 하고 싶은 일을 고른다(사용자 지시, 2026-08-13). 비워두면 모든 활동을
    # 대상으로 탐색한다. 절약 수단(Category)은 더 이상 이 요청의 필드가 아니다 —
    # SaveMap이 내부적으로 자동 탐색한다(할인/무료/마감세일/쿠폰/결제수단할인/지역혜택
    # 전부 대상, rank_candidates가 점수로 알아서 우선순위를 매김).
    activities: list[RouteActivity] = Field(default_factory=list)
    # "무료주차 필요" — Step2 조건 중 유일하게 하드 필터로 동작한다(무료주차 데이터가
    # 없는 후보는 절대 지어내지 않고 그냥 빼버린다). 나머지 조건(최대한 저렴하게/
    # 검증된 정보 우선/최신 정보 우선/이동거리 최소화)은 아래 preference로 정렬만
    # 바꾼다 — preference와 달리 이건 "있어야만 하는 조건"이라 필터가 맞다.
    free_parking_required: bool = False
    # "어떤 조건이 중요할까요?" — 단일 선택(라디오). None이면 기존 기본 정렬
    # (절약률 0.7 + 신뢰도 0.3 가중 점수, ranker.py)을 그대로 쓴다.
    preference: RoutePreference | None = None
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
