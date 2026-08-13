from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
from app.api.schemas.user import SavingsSummaryResponse
from app.gamification.service import get_savings_summary

router = APIRouter(tags=["users"], prefix="/users")


@router.get("/me/savings-summary", response_model=SavingsSummaryResponse)
async def my_savings_summary(
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> SavingsSummaryResponse:
    summary = await get_savings_summary(session, user_id)
    return SavingsSummaryResponse(
        total_saved=summary.total_saved,
        level=summary.level,
        title=summary.title,
        next_threshold=summary.next_threshold,
        remaining_to_next=summary.remaining_to_next,
        progress_pct=summary.progress_pct,
        certification_count=summary.certification_count,
        monthly_saved=summary.monthly_saved,
    )
