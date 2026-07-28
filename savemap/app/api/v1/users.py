from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, UserDep
from app.api.schemas.user import XpSummaryResponse
from app.gamification.service import get_xp_summary

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
