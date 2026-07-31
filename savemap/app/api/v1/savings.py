from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
from app.api.schemas.savings import CertificationResponse, CertifyRequest
from app.gamification.certification import certify_savings

router = APIRouter(tags=["savings"])


@router.post("/offers/{offer_id}/certify", response_model=CertificationResponse, status_code=201)
async def certify_offer(
    offer_id: int,
    payload: CertifyRequest,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> CertificationResponse:
    cert, summary, xp_awarded = await certify_savings(
        session,
        user_id,
        offer_id,
        method=payload.method,
        actual_price=payload.actual_price,
        receipt_image_url=payload.receipt_image_url,
    )
    return CertificationResponse(
        id=cert.id,
        offer_id=cert.offer_id,
        place_name=cert.place_name,
        base_price=float(cert.base_price),
        actual_price=float(cert.actual_price),
        amount=float(cert.amount),
        method=cert.method,
        confidence=cert.confidence,
        created_at=cert.created_at,
        total_saved=summary.total_saved,
        level=summary.level,
        title=summary.title,
        xp_awarded=xp_awarded,
    )
