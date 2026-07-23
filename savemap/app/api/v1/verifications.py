from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, UserDep
from app.api.schemas.verification import VerificationCreate, VerificationResponse
from app.sources.user_verification.service import submit_verification

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
