from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MissingReportImageError
from app.domain.enums import ReportStatus
from app.domain.report import UserReport


async def create_report(session: AsyncSession, user_id: str, image_url: str) -> UserReport:
    if not image_url:
        raise MissingReportImageError()
    report = UserReport(user_id=user_id, image_url=image_url, status=ReportStatus.PENDING)
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


async def list_pending(session: AsyncSession, limit: int = 50) -> list[UserReport]:
    stmt = (
        select(UserReport)
        .where(UserReport.status == ReportStatus.PENDING)
        .order_by(UserReport.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
