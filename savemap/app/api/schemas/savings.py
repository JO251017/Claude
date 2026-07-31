from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import CertificationConfidence, CertificationMethod


class CertifyRequest(BaseModel):
    method: CertificationMethod = CertificationMethod.SIMPLE
    actual_price: float | None = None
    receipt_image_url: str | None = None


class CertificationResponse(BaseModel):
    id: int
    offer_id: int | None
    place_name: str
    base_price: float
    actual_price: float
    amount: float
    method: CertificationMethod
    confidence: CertificationConfidence
    created_at: datetime
    total_saved: float
    level: int
    title: str
    xp_awarded: int
