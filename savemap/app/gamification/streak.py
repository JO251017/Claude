from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.savings import SavingsCertification
from app.domain.store_visit import PlaceRecommendation, StoreStatusUpdate

# 연속 방문 스트릭(2026-08-30, "재미 개선 — 연속 방문 스트릭") — 발견하기/영수증
# (또는 직접입력) 인증/추천 중 하나라도 한 날을 "활동한 날"로 센다. 프론트의
# growthScore(discovered_place_count + visit_count + recommend_count)와 정확히
# 같은 세 축이라, "오늘 뭘 해야 스트릭이 이어지나"와 "오늘 뭘 해야 펫이 크나"가
# 사용자 입장에서 같은 질문이 되게 맞췄다.
#
# 발견 쪽은 매장별로 딱 한 행만 남기는 StoreInterest(discovered_place_count가
# 쓰는 테이블)가 아니라 원본 이벤트 로그인 StoreStatusUpdate를 쓴다 — 같은
# 매장을 다시 발견하면 StoreInterest는 last_interested_at만 최신 날짜로 덮어써서
# 그 전에 있었던 "그날 발견했다"는 기록 자체가 사라진다. 스트릭은 날짜별
# 이력이 온전히 남아야 하므로 이벤트 로그 쪽이 맞다 — discovered_place_count(뱃지용,
# 서로 다른 매장 수)와는 성격이 다른, 별개의 정직한 지표다.
_STREAK_LOOKBACK_DAYS = 400  # 이보다 오래된 활동은 지금 스트릭 계산에 필요 없다


@dataclass
class StreakSummary:
    current_streak: int
    did_activity_today: bool
    at_risk: bool  # 스트릭이 있는데 오늘 아직 활동을 안 해서, 오늘 안에 안 하면 끊긴다


def _to_kst_date(ts: datetime) -> date:
    return (ts + timedelta(hours=9)).date()


async def get_streak_summary(session: AsyncSession, user_id: str) -> StreakSummary:
    since = datetime.now(UTC) - timedelta(days=_STREAK_LOOKBACK_DAYS)

    cert_rows = (
        await session.execute(
            select(SavingsCertification.created_at).where(
                SavingsCertification.user_id == user_id,
                SavingsCertification.created_at >= since,
            )
        )
    ).scalars().all()
    discover_rows = (
        await session.execute(
            select(StoreStatusUpdate.created_at).where(
                StoreStatusUpdate.user_id == user_id,
                StoreStatusUpdate.created_at >= since,
            )
        )
    ).scalars().all()
    recommend_rows = (
        await session.execute(
            select(PlaceRecommendation.created_at).where(
                PlaceRecommendation.user_id == user_id,
                PlaceRecommendation.created_at >= since,
            )
        )
    ).scalars().all()

    activity_dates = {_to_kst_date(ts) for ts in (*cert_rows, *discover_rows, *recommend_rows)}

    today = _to_kst_date(datetime.now(UTC))
    did_activity_today = today in activity_dates

    # 오늘 아직 활동을 안 했으면 어제부터 거슬러 올라간다 — "오늘 안에만 하면
    # 이어지는" 상태의 스트릭 길이를 그대로 보여주기 위함(오늘 걸 억지로 0으로
    # 만들지 않는다).
    cursor = today if did_activity_today else today - timedelta(days=1)
    streak = 0
    while cursor in activity_dates:
        streak += 1
        cursor -= timedelta(days=1)

    return StreakSummary(
        current_streak=streak,
        did_activity_today=did_activity_today,
        at_risk=(not did_activity_today) and streak > 0,
    )
