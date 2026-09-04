from pydantic import BaseModel, Field

from app.api.schemas.search import SearchResultItem
from app.domain.enums import PaymentMethodType, RouteActivity, RoutePreference


class RouteContext(BaseModel):
    """사용자가 "어떤 상황"에서 코스를 쓰는지 — 지금은 인원수 하나뿐이다. 구조
    재설계 제안서(2026-08-13, "SaveMap 구조 재설계 제안서" §3) 진단: Activity/
    Constraint/Preference는 이미 별도 개념으로 분리돼 있는데 Context는 이름조차
    없어서, 동행(가족/혼자 등)·이동수단·시간대처럼 향후 자연어 입력에서 나올
    필드를 담을 자리가 없었다. 지금은 party_size 하나뿐이라도 그룹을 미리 만들어
    두면 나중에 필드를 추가할 때 budget/preference와 경계가 겹치는 리팩터링을
    다시 하지 않아도 된다 — 새 기능이 아니라 이름 붙이기다."""

    party_size: int = Field(default=1, ge=1, le=20)


class RouteConstraints(BaseModel):
    """반드시 지켜야 하는 조건. 셋 다 "동작은 이미" 하드 제약이다 — budget/
    radius_km를 벗어나면 결과 자체가 안 나오고(SM4003/SM4002), free_parking_required는
    rule_filter가 만족 못 하는 후보를 아예 제거한다. 반면 preference(RoutePreference)는
    후보를 자르지 않고 순서만 바꾸는 소프트 기준이라 성격이 다르다 — 그래서
    Preference와 나란한 필드로 두지 않고 별도 그룹으로 뺐다."""

    budget: float = Field(gt=0)
    radius_km: float | None = None
    # "무료주차 필요" — 무료주차 데이터가 없는 후보는 절대 지어내지 않고 그냥
    # 빼버린다(하드 필터). 오퍼 하나엔 절약수단이 하나뿐이라(도메인 제약)
    # "식사 오퍼 + 곁다리 무료주차" 조합은 지금 데이터 모델로는 표현 못 한다(v1 한계).
    free_parking_required: bool = False


class RouteSuggestRequest(BaseModel):
    lat: float
    lng: float
    # "무엇을 할까요?" — 할인/무료/마감세일 같은 절약 수단(Category)이 아니라 사용자가
    # 실제로 하고 싶은 일을 고른다(사용자 지시, 2026-08-13). 비워두면 모든 활동을
    # 대상으로 탐색한다. 절약 수단(Category)은 더 이상 이 요청의 필드가 아니다 —
    # SaveMap이 내부적으로 자동 탐색한다(할인/무료/마감세일/쿠폰/결제수단할인/지역혜택
    # 전부 대상, rank_candidates가 점수로 알아서 우선순위를 매김).
    activities: list[RouteActivity] = Field(default_factory=list)
    context: RouteContext = Field(default_factory=RouteContext)
    constraints: RouteConstraints
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
