from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.report import UserReport


async def list_recent(session: AsyncSession, limit: int = 50) -> list[UserReport]:
    """"최근 제보" 피드용 — 예전엔 status == PENDING만 걸러서(list_pending) 지금은
    쓰는 이름이 잘못됐었다. 제보가 즉시 게시되면서(2026-08-18, ReportPipeline.ingest)
    VERIFIED로 바뀌는데, 그것도 그대로 필터링돼서 "최근 제보"에서 사라져
    보였을 것 — 상태와 무관하게 최신순으로 다 보여준다."""
    stmt = select(UserReport).order_by(UserReport.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())
