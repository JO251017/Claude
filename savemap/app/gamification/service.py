from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import XP_REWARD, XpReason
from app.domain.xp import XpLedger

# (가정) 레벨당 필요 경험치. 기획서에 명시된 값이 없어 임의로 설정.
XP_PER_LEVEL = 50

# 기획서(SUB 기획서_260723) 기준 레벨 구간별 칭호.
LEVEL_TITLES: list[tuple[int, int | None, str]] = [
    (1, 9, "짠지망생"),
    (10, 29, "절약 탐험가"),
    (30, 49, "혜택 마스터"),
    (50, None, "절약의 신"),
]


@dataclass
class XpSummary:
    total_xp: int
    level: int
    title: str
    xp_into_level: int
    xp_per_level: int


def compute_level(total_xp: int) -> XpSummary:
    total_xp = max(total_xp, 0)
    level = total_xp // XP_PER_LEVEL + 1
    title = next(t for lo, hi, t in LEVEL_TITLES if hi is None or lo <= level <= hi)
    return XpSummary(
        total_xp=total_xp,
        level=level,
        title=title,
        xp_into_level=total_xp % XP_PER_LEVEL,
        xp_per_level=XP_PER_LEVEL,
    )


async def award_xp(session: AsyncSession, user_id: str, reason: XpReason) -> int:
    delta = XP_REWARD[reason]
    session.add(XpLedger(user_id=user_id, delta=delta, reason=reason))
    await session.commit()
    return delta


async def get_xp_summary(session: AsyncSession, user_id: str) -> XpSummary:
    total = (
        await session.execute(select(func.coalesce(func.sum(XpLedger.delta), 0)).where(XpLedger.user_id == user_id))
    ).scalar_one()
    return compute_level(int(total))


class LeaderboardService:
    async def weekly_top(self, region: str, limit: int = 10) -> list[dict]:
        raise NotImplementedError("길드·랭킹보드는 후속 단계에서 구현")
