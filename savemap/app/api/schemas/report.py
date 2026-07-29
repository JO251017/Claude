from pydantic import BaseModel

from app.domain.enums import Category, ReportStatus


class ReportCreate(BaseModel):
    image_url: str
    lat: float | None = None
    lng: float | None = None


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
