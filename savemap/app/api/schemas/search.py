from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Category, Layer, PaymentMethodType


class SavingsReportItem(BaseModel):
    """SaveMap의 핵심 콘텐츠. 메뉴가 아니라 "얼마나 절약되고 얼마나 믿을 수 있는지"를
    실제 집계 데이터만으로 계산한 결과 — 데이터가 부족하면 score/grade는 null이고
    confidence_tier가 "low"로 내려간다 (지어내지 않기)."""

    score: int | None = None
    grade: str | None = None
    confidence_tier: str
    confidence_stars: int  # 0, 2, 3, 4, 5 중 하나 (0 = 데이터 부족, 별을 그리지 않음)
    confidence_label: str
    reasons: list[str] = []
    one_line: str = ""


class SignatureMenuItem(BaseModel):
    """대표메뉴 한 줄. 실제 등록된 메뉴 가격(사장님 등록 또는 사진 제보)에서만 나온다 —
    전체 메뉴판은 카카오맵의 역할이고, SaveMap은 절약 계산에 쓰인 대표메뉴 하나만 보여준다."""

    name: str
    price: float


class SearchResultItem(BaseModel):
    offer_id: int
    place_id: int
    place_name: str
    category_name: str | None = None
    business_status: str | None = None
    report: SavingsReportItem | None = None
    signature_menu: SignatureMenuItem | None = None
    recommend_count: int = 0
    kakao_url: str | None = None
    address: str | None = None
    phone: str | None = None
    category: Category
    # FLASH면 프론트가 마감 카운트다운 배지를 보여준다(2026-08-18, "마감임박
    # 긴급성 되살리기" — rule_filter.py 참고). 지금까진 검색에서 FLASH 자체가
    # 아예 빠져 있어서 이 값을 쓸 일도 없었다.
    layer: Layer
    distance_m: float
    lat: float
    lng: float
    base_price: float
    final_price: float
    total_savings: float
    savings_rate: float
    # "region"=주변 매장 실측가와 비교, "ai"=Gemini 추정 통상가와 비교, None=비교 대상 없음.
    # 프론트가 절약치를 실측처럼 오해하지 않고 출처를 그대로 밝힐 수 있게 한다.
    savings_source: str | None = None
    expires_at: datetime | None = None
    trust_score: float
    verification_count: int = 0
    last_verified_at: datetime | None = None
    discover_count: int = 0
    dining_count: int = 0
    score: float
    # 전국지역화폐가맹점표준데이터(지자체 공식 명단)와 매칭돼 검증된 매장인지 —
    # 가격/할인 계산과는 무관한 정보 확인용 값이다(이 데이터엔 금액이 없어서
    # savings_* 필드 어디에도 영향을 주지 않는다). False가 곧 "미가맹"을 뜻하진
    # 않는다 — 아직 매칭을 안 돌렸거나 명단에 없을 수 있다(지어내지 않기).
    accepts_local_currency: bool = False


class DiscoveredPlaceItem(BaseModel):
    """SaveMap에 아직 가격/절약 정보(Offer)가 없는 주변 식당·카페. 두 소스에서 채워진다 —
    (1) 카카오 로컬 검색으로 실시간 발견한 곳(place_id 없음), (2) 인허가 데이터 등으로
    이미 SaveMap DB에 Place는 있지만 아직 Offer가 안 붙은 곳(place_id 있음, kakao_place_id는
    없을 수 있음). place_id가 있으면 메뉴 제보 시 그 Place에 바로 붙여서 새 매장을
    중복 생성하지 않는다. 콜드스타트 문제(지도가 텅 비는 것) 완화용."""

    place_id: int | None = None
    kakao_place_id: str | None = None
    place_name: str
    address: str | None = None
    category_name: str | None = None
    phone: str | None = None
    distance_m: float
    lat: float
    lng: float
    kakao_url: str | None = None


class WeatherInfo(BaseModel):
    """검색 중심 좌표의 현재 날씨(기상청 초단기실황). 랭킹에 쓰인 것과 같은 값을
    그대로 노출해서 "왜 카페가 위로 왔지"를 프론트/사용자가 그대로 확인할 수 있게
    한다 — 조회에 실패하거나 키 미설정이면 이 필드 자체가 null(지어내지 않기)."""

    condition: str  # "rain" | "snow" | "clear"
    temp_c: float | None = None
    icon: str
    label: str


class SearchResponse(BaseModel):
    count: int
    radius_km: float
    results: list[SearchResultItem]
    discovered_places: list[DiscoveredPlaceItem] = []
    weather: WeatherInfo | None = None


class SearchQuery(BaseModel):
    lat: float
    lng: float
    radius_km: float | None = None
    category: Category | None = None
    payment_methods: list[PaymentMethodType] = Field(default_factory=list)
