from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ReportStatus
from app.domain.report import UserReport


async def list_pending(session: AsyncSession, limit: int = 50) -> list[UserReport]:
    stmt = (
        select(UserReport)
        .where(UserReport.status == ReportStatus.PENDING)
        .order_by(UserReport.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
