from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
from app.api.schemas.exchange import AssetCreate, AssetResponse
from app.domain.savings import SavingsAsset
from app.exchange import service

router = APIRouter(tags=["exchange"], prefix="/exchange")


def _asset_response(asset: SavingsAsset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        category=asset.category,
        title=asset.title,
        condition_text=asset.condition_text,
        estimated_value=asset.estimated_value,
        expires_at=asset.expires_at,
        status=asset.status,
        created_at=asset.created_at,
        offer_id=asset.offer_id,
        place_id=asset.place_id,
        place_name=asset.place_name,
    )


@router.post("/assets", response_model=AssetResponse, status_code=201)
async def create_asset(
    payload: AssetCreate,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> AssetResponse:
    asset = await service.create_asset(
        session,
        user_id,
        category=payload.category,
        title=payload.title,
        condition_text=payload.condition_text,
        estimated_value=payload.estimated_value,
        expires_at=payload.expires_at,
        offer_id=payload.offer_id,
        place_id=payload.place_id,
        place_name=payload.place_name,
    )
    return _asset_response(asset)


@router.get("/assets", response_model=list[AssetResponse])
async def list_assets(
    category: str | None = Query(default=None),
    session: AsyncSession = SessionDep,
) -> list[AssetResponse]:
    assets = await service.list_available_assets(session, category)
    return [_asset_response(a) for a in assets]


@router.get("/assets/mine", response_model=list[AssetResponse])
async def list_my_assets(
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> list[AssetResponse]:
    assets = await service.list_my_assets(session, user_id)
    return [_asset_response(a) for a in assets]


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: int,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> None:
    await service.delete_asset(session, user_id, asset_id)
