from pydantic import BaseModel

from app.domain.enums import Category, ReportStatus


class ReportCreate(BaseModel):
    image_url: str
    lat: float | None = None
    lng: float | None = None
    # POST /v1/reports/analyze 결과를 사용자가 확인/수정한 뒤 넘기는 값.
    # 제공되면 서버는 AI를 재호출하지 않고 이 값을 그대로 사용한다.
    title: str | None = None
    price: float | None = None
    category: Category | None = None
    # 제보 → 실제 게시(2026-08-18) — Place.name에 쓸 매장명. title(혜택 내용,
    # 예: "삼겹살 20% 할인")과는 다른 축이라 별도 필드로 받는다.
    place_name: str | None = None
    # 할인 전 정가. price(할인가/실제 본 가격)와 같이 있어야 진짜 절약액을
    # 계산할 수 있다 — 없으면 지어내지 않고 가격 정보 없이 게시한다.
    regular_price: float | None = None


class ReportResponse(BaseModel):
    id: int
    user_id: str
    image_url: str
    ai_category: Category | None = None
    status: ReportStatus
    ocr_price: float | None = None
    ocr_title: str | None = None
    has_location: bool = False
    # 제보 → 실제 게시(2026-08-18) — 위치가 확보돼 Place/Offer가 실제로
    # 만들어졌으면 채워진다. None이면 아직 지도에 안 뜬 상태(위치 정보 없음).
    place_id: int | None = None
    offer_id: int | None = None


class RecentReportItem(BaseModel):
    id: int
    ai_category: Category | None = None
    status: ReportStatus
    ocr_title: str | None = None
    ocr_price: float | None = None


class ReportAnalyzeResponse(BaseModel):
    image_url: str
    ai_category: Category | None = None
    ocr_price: float | None = None
    ocr_title: str | None = None
    lat: float | None = None
    lng: float | None = None
    # 제보 → 실제 게시(2026-08-18) — Gemini가 사진에서 읽은 가게 이름/주소 추정값.
    # 확인 화면의 "장소명" 입력을 미리 채워주는 용도(사용자가 다시 타이핑 안 해도 됨).
    location_text: str | None = None
