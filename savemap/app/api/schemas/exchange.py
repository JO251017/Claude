from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import AssetStatus


class AssetCreate(BaseModel):
    category: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    condition_text: str | None = None
    estimated_value: float | None = None
    expires_at: datetime | None = None


class AssetResponse(BaseModel):
    id: int
    category: str
    title: str
    condition_text: str | None
    estimated_value: float | None
    expires_at: datetime | None
    status: AssetStatus
    created_at: datetime
