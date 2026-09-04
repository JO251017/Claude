"""AI Price Discovery Engine — 가격 커버리지 KPI(지시서 28-24/28-25/28-26).

전부 실제 DB 집계 쿼리다 — 임의 숫자를 쓰지 않는다. "가격 있는 매장"의 정의는
app/api/v1/admin.py의 GET /admin/places/stats가 이미 쓰는 것과 정확히 같다
(MenuItem이 하나 이상 있는 Place) — 새 기준을 만들지 않는다."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.domain.price_discovery import DiscoveryJobStatus, PriceDiscoveryJob


async def get_discovery_metrics(session: AsyncSession, *, region: str | None = None) -> dict:
    filters = [Place.address.ilike(f"%{region}%")] if region else []

    stores_total = (
        await session.execute(select(func.count()).select_from(Place).where(*filters))
    ).scalar_one()
    stores_with_price = (
        await session.execute(
            select(func.count(func.distinct(MenuItem.place_id)))
            .select_from(MenuItem)
            .join(Place, MenuItem.place_id == Place.id)
            .where(*filters)
        )
    ).scalar_one()

    job_filters = [Place.address.ilike(f"%{region}%")] if region else []
    job_counts_stmt = (
        select(PriceDiscoveryJob.status, func.count())
        .select_from(PriceDiscoveryJob)
        .join(Place, PriceDiscoveryJob.place_id == Place.id)
        .where(*job_filters)
        .group_by(PriceDiscoveryJob.status)
    )
    job_counts = {row[0]: row[1] for row in (await session.execute(job_counts_stmt)).all()}

    completed = job_counts.get(DiscoveryJobStatus.COMPLETED, 0)
    manual_review = job_counts.get(DiscoveryJobStatus.MANUAL_REVIEW, 0)
    failed = job_counts.get(DiscoveryJobStatus.FAILED, 0)
    pending = job_counts.get(DiscoveryJobStatus.PENDING, 0)
    processing = job_counts.get(DiscoveryJobStatus.PROCESSING, 0)

    # "완료된 job"(28-25) = 종결 상태(성공/검토대기/실패) 전체. discovery_success_rate는
    # 완전 자동 성공(COMPLETED)만 성공으로 센다 — manual_review는 아직 확정 전이라
    # 성공으로 잡으면 실제보다 낙관적인 숫자가 된다.
    finished = completed + manual_review + failed
    success_rate = round(completed / finished, 3) if finished else None

    return {
        "region_filter": region,
        "stores_total": stores_total,
        "stores_with_price": stores_with_price,
        "coverage": round(stores_with_price / stores_total, 3) if stores_total else 0.0,
        "jobs": {
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "manual_review": manual_review,
            "failed": failed,
        },
        "discovery_success_rate": success_rate,
    }
