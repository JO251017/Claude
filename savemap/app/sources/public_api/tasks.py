import asyncio

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.sources.public_api.service import sync_all_public_sources


async def _run() -> dict:
    async with SessionLocal() as session:
        return await sync_all_public_sources(session)


@celery_app.task(name="sources.public_api.sync_all")
def sync_all() -> dict:
    """collect → validate → dedupe → upsert 배치 실행.

    참고: 현재 Render 배포(render.yaml)에는 이 태스크를 실제로 소비할 Celery worker/beat
    프로세스가 없다 (무료 플랜, 웹 서비스 1개뿐) — 이 태스크 자체는 정상 구현되어 있지만,
    지금은 POST /v1/admin/sync/public-data 로 직접 트리거해야 실제로 실행된다.
    """
    return asyncio.run(_run())
