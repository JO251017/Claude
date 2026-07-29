from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep, UserDep
from app.api.schemas.user import SavingsSummaryResponse, XpSummaryResponse
from app.gamification.service import get_savings_summary, get_xp_summary

router = APIRouter(tags=["users"], prefix="/users")


@router.get("/me/xp", response_model=XpSummaryResponse)
async def my_xp(
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> XpSummaryResponse:
    summary = await get_xp_summary(session, user_id)
    return XpSummaryResponse(
        total_xp=summary.total_xp,
        level=summary.level,
        title=summary.title,
        xp_into_level=summary.xp_into_level,
        xp_per_level=summary.xp_per_level,
    )


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
    )
