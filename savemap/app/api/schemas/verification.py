from pydantic import BaseModel

from app.domain.enums import Verdict


class VerificationCreate(BaseModel):
    report_id: int
    verdict: Verdict
    weight: float = 1.0


class VerificationResponse(BaseModel):
    report_id: int
    trust_score: float
