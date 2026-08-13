from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import AssetStatus


class AssetCreate(BaseModel):
    category: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    condition_text: str | None = None
    estimated_value: float | None = None
    expires_at: datetime | None = None
    # EXCHANGE 재도입(2026-08-13) — 오퍼 상세 "저장하기"로 만든 자산에만 채워짐.
    # 기존 자유입력 등록 폼은 이 필드들을 안 보내므로 기본값 None으로 하위호환.
    offer_id: int | None = None
    place_id: int | None = None
    place_name: str | None = Field(default=None, max_length=255)


class AssetResponse(BaseModel):
    id: int
    category: str
    title: str
    condition_text: str | None
    estimated_value: float | None
    expires_at: datetime | None
    status: AssetStatus
    created_at: datetime
    offer_id: int | None = None
    place_id: int | None = None
    place_name: str | None = None
