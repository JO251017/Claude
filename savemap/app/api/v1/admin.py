from fastapi import APIRouter, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.errors import AuthenticationRequiredError
from app.sources.public_api.good_price import sync_good_price_stores
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


@router.post("/sync/good-price-stores")
async def trigger_good_price_sync(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전국"),
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = SessionDep,
) -> dict:
    """행정안전부 착한가격업소(정부 지정 저렴 업소 + 실제 대표메뉴 가격)를 가져와
    Place/MenuItem으로 저장한다 — 초기 사용자에게 보여줄 실제 절약 정보의 콜드스타트 시드.
    전국 한 번에 넣으면 Render 무료 플랜 요청 제한에 걸릴 수 있으니 region으로 나눠 실행 권장."""
    if not settings.admin_sync_key or x_admin_key != settings.admin_sync_key:
        raise AuthenticationRequiredError("관리자 키가 필요합니다 (X-Admin-Key 헤더)")
    return await sync_good_price_stores(session, region=region)
