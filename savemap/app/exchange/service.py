from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AssetNotFoundError
from app.domain.enums import AssetStatus
from app.domain.savings import SavingsAsset


async def create_asset(
    session: AsyncSession,
    owner_user_id: str,
    category: str,
    title: str,
    condition_text: str | None,
    estimated_value: float | None,
    expires_at: datetime | None,
    offer_id: int | None = None,
    place_id: int | None = None,
    place_name: str | None = None,
) -> SavingsAsset:
    asset = SavingsAsset(
        owner_user_id=owner_user_id,
        category=category,
        title=title,
        condition_text=condition_text,
        estimated_value=estimated_value,
        expires_at=expires_at,
        status=AssetStatus.AVAILABLE,
        offer_id=offer_id,
        place_id=place_id,
        place_name=place_name,
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return asset


async def list_available_assets(session: AsyncSession, category: str | None = None) -> list[SavingsAsset]:
    stmt = select(SavingsAsset).where(SavingsAsset.status == AssetStatus.AVAILABLE)
    if category:
        stmt = stmt.where(SavingsAsset.category == category)
    stmt = stmt.order_by(SavingsAsset.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def list_my_assets(session: AsyncSession, owner_user_id: str) -> list[SavingsAsset]:
    stmt = (
        select(SavingsAsset)
        .where(SavingsAsset.owner_user_id == owner_user_id)
        .order_by(SavingsAsset.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _get_owned_asset(session: AsyncSession, owner_user_id: str, asset_id: int) -> SavingsAsset:
    stmt = select(SavingsAsset).where(
        SavingsAsset.id == asset_id, SavingsAsset.owner_user_id == owner_user_id
    )
    asset = (await session.execute(stmt)).scalar_one_or_none()
    if asset is None:
        raise AssetNotFoundError()
    return asset


async def delete_asset(session: AsyncSession, owner_user_id: str, asset_id: int) -> None:
    asset = await _get_owned_asset(session, owner_user_id, asset_id)
    await session.delete(asset)
    await session.commit()
