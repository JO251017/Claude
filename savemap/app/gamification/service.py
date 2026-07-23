from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import XP_REWARD, XpReason
from app.domain.xp import XpLedger


async def award_xp(session: AsyncSession, user_id: str, reason: XpReason) -> int:
    delta = XP_REWARD[reason]
    session.add(XpLedger(user_id=user_id, delta=delta, reason=reason))
    await session.commit()
    return delta


class LeaderboardService:
    async def weekly_top(self, region: str, limit: int = 10) -> list[dict]:
        raise NotImplementedError("길드·랭킹보드는 후속 단계에서 구현")
