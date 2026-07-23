from pydantic import BaseModel

from app.domain.enums import Category, ReportStatus


class ReportCreate(BaseModel):
    image_url: str


class ReportResponse(BaseModel):
    id: int
    user_id: str
    image_url: str
    ai_category: Category | None = None
    status: ReportStatus
