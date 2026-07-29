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


class ReportResponse(BaseModel):
    id: int
    user_id: str
    image_url: str
    ai_category: Category | None = None
    status: ReportStatus
    ocr_price: float | None = None
    ocr_title: str | None = None
    has_location: bool = False


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
