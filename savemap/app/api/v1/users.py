from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
from app.api.schemas.user import (
    DailySavedPointResponse,
    DigestResponse,
    MerchantStatusResponse,
    PetReactionResponse,
    SavingsSummaryResponse,
)
from app.engine.savings_digest import get_or_create_digest
from app.gamification.pet_reactions import get_or_create_levelup_message
from app.gamification.service import (
    compute_visit_title,
    get_daily_saved_series,
    get_explorer_summary,
    get_growth_score,
    get_recommend_summary,
    get_savings_summary,
)
from app.gamification.streak import get_streak_summary
from app.sources.merchant_console.service import is_merchant_verified

router = APIRouter(tags=["users"], prefix="/users")


@router.get("/me/merchant-status", response_model=MerchantStatusResponse)
async def my_merchant_status(
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> MerchantStatusResponse:
    """MY 탭이 "사업자 콘솔" 바로가기를 보여줄지 결정하려고 호출한다(2-3,
    2026-08-13). savings-summary에 필드를 더 얹는 대신 별도 엔드포인트로 분리했다
    — savings-summary가 이미 필드가 많아지고 있어서."""
    verified = await is_merchant_verified(session, user_id)
    return MerchantStatusResponse(is_verified_merchant=verified)


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
    streak = await get_streak_summary(session, user_id)
    growth_score = await get_growth_score(
        session,
        user_id,
        discovered_place_count=explorer.discovered_place_count,
        recommend_count=recommend.recommend_count,
    )
    daily_saved = await get_daily_saved_series(session, user_id)
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
        streak_days=streak.current_streak,
        streak_active_today=streak.did_activity_today,
        streak_at_risk=streak.at_risk,
        growth_score=growth_score,
        daily_saved=[DailySavedPointResponse(date=p.date, amount=p.amount) for p in daily_saved],
    )


@router.get("/me/digest", response_model=DigestResponse)
async def my_digest(
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> DigestResponse:
    """AI 활용 확대 안건 C(2026-08-31) — 개인화 절약 다이제스트. 이번 주 캐시가
    있으면 그대로, 없으면 이 자리에서 한 번 생성해 캐시한다(Render 무료 플랜에
    크론이 없어 온디맨드 방식)."""
    text, source = await get_or_create_digest(session, user_id)
    return DigestResponse(summary_text=text, source=source)


@router.get("/me/pet-reaction", response_model=PetReactionResponse)
async def my_pet_reaction(
    stage_index: int = Query(ge=0, le=64, description="프론트 AVATAR_GROWTH_STAGES의 stageIndex"),
    stage_name: str = Query(max_length=40, description="그 단계 이름(프론트가 이미 계산해 둔 값)"),
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> PetReactionResponse:
    """AI MVP §D(2026-09-01) — 펫 레벨업 축하 대사. 이 stage_index에 대한 전역
    캐시가 있으면 그대로, 없으면 이 자리에서 한 번만 생성해 캐시한다(사용자별이
    아니라 단계별 전역 캐시 — get_or_create_levelup_message 참고). 발견/방문/
    추천/제보/인증/스트릭 등 다른 이벤트는 이 엔드포인트를 안 쓴다 — 그쪽은
    프론트 템플릿 로테이션만으로 충분하다(§5 AI 호출 비용 최소화)."""
    text, source = await get_or_create_levelup_message(session, stage_index, stage_name)
    return PetReactionResponse(message=text, source=source)
