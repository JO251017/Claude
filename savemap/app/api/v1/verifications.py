from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, UserDep
from app.api.schemas.verification import (
    OfferVerificationCreate,
    OfferVerificationResponse,
    VerificationCreate,
    VerificationResponse,
)
from app.sources.user_verification.service import submit_offer_verification, submit_verification

router = APIRouter(tags=["verifications"])


@router.post("/verifications", response_model=VerificationResponse, status_code=201)
async def create_verification(
    payload: VerificationCreate,
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> VerificationResponse:
    score = await submit_verification(
        session, payload.report_id, user_id, payload.verdict, payload.weight
    )
    return VerificationResponse(report_id=payload.report_id, trust_score=score)


@router.post("/offers/{offer_id}/verify", response_model=OfferVerificationResponse, status_code=201)
async def create_offer_verification(
    offer_id: int,
    payload: OfferVerificationCreate,
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> OfferVerificationResponse:
    score, count, last_at = await submit_offer_verification(
        session, offer_id, user_id, payload.verdict
    )
    return OfferVerificationResponse(
        offer_id=offer_id, trust_score=score, verification_count=count, last_verified_at=last_at
    )
