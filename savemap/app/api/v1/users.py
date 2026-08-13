from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
from app.api.schemas.user import SavingsSummaryResponse
from app.gamification.service import (
    compute_visit_title,
    get_explorer_summary,
    get_recommend_summary,
    get_savings_summary,
)

router = APIRouter(tags=["users"], prefix="/users")


@router.get("/me/savings-summary", response_model=SavingsSummaryResponse)
async def my_savings_summary(
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> SavingsSummaryResponse:
    summary = await get_savings_summary(session, user_id)
    explorer = await get_explorer_summary(session, user_id)
    # 방문 횟수 칭호는 새 쿼리 없이 위에서 이미 구한 certification_count를 그대로
    # 쓴다(사용자 확정: "영수증 인증을 방문횟수로 해").
    visit = compute_visit_title(summary.certification_count)
    recommend = await get_recommend_summary(session, user_id)
    return SavingsSummaryResponse(
        total_saved=summary.total_saved,
        level=summary.level,
        title=summary.title,
        next_threshold=summary.next_threshold,
        remaining_to_next=summary.remaining_to_next,
        progress_pct=summary.progress_pct,
        certification_count=summary.certification_count,
        monthly_saved=summary.monthly_saved,
        today_saved=summary.today_saved,
        weekly_saved=summary.weekly_saved,
        yearly_saved=summary.yearly_saved,
        discovered_place_count=explorer.discovered_place_count,
        explorer_title=explorer.title,
        explorer_next_threshold=explorer.next_threshold,
        explorer_remaining_to_next=explorer.remaining_to_next,
        visit_count=visit.visit_count,
        visit_title=visit.title,
        visit_next_threshold=visit.next_threshold,
        visit_remaining_to_next=visit.remaining_to_next,
        recommend_count=recommend.recommend_count,
        recommend_title=recommend.title,
        recommend_next_threshold=recommend.next_threshold,
        recommend_remaining_to_next=recommend.remaining_to_next,
    )
