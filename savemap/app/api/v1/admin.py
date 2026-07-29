from fastapi import APIRouter, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.errors import AuthenticationRequiredError
from app.sources.public_api.service import sync_all_public_sources

router = APIRouter(tags=["admin"], prefix="/admin")


@router.post("/sync/public-data")
async def trigger_public_data_sync(
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = SessionDep,
) -> dict:
    """공공데이터 수집을 즉시 실행한다. Celery worker가 없는 배포 환경(현재 Render 무료 플랜)에서
    수동/크론으로 동기화를 트리거하기 위한 엔드포인트. ADMIN_SYNC_KEY 미설정 시 항상 거부된다."""
    if not settings.admin_sync_key or x_admin_key != settings.admin_sync_key:
        raise AuthenticationRequiredError("관리자 키가 필요합니다 (X-Admin-Key 헤더)")
    return await sync_all_public_sources(session)
