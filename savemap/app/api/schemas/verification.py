from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import Verdict


class VerificationCreate(BaseModel):
    report_id: int
    verdict: Verdict
    weight: float = 1.0


class VerificationResponse(BaseModel):
    report_id: int
    trust_score: float


class OfferVerificationCreate(BaseModel):
    verdict: Verdict


class OfferVerificationResponse(BaseModel):
    offer_id: int
    trust_score: float
    verification_count: int
    last_verified_at: datetime | None = None
