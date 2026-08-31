"""AI Price Discovery Engine — price_publisher 단계(지시서 28-35).

새 저장 경로를 만들지 않는다 — 승인된 가격은 기존 app/engine/offer_sync.py:
sync_menu_offer 파이프라인에 그대로 태워서, savings_calculator/ranker가
자동으로 집어먹게 한다. 이 함수 자체는 여기서 처음 저장되는 MenuItem을
만드는 부분만 담당한다(place에 이미 다른 메뉴가 있는 경우는 candidate_selector가
애초에 후보에서 걸러내므로 여기서는 항상 신규 생성이다)."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.offer_sync import sync_menu_offer
from app.engine.price_discovery.confidence_engine import resolve_source_type
from app.engine.price_discovery.price_validator import PriceVerdict, ValidatedPrice


async def publish_prices(
    session: AsyncSession, place: Place, validated_prices: list[ValidatedPrice]
) -> list[MenuItem]:
    """verdict가 VALID인 항목만 즉시 게시한다 — NEEDS_REVIEW는 여기서 건드리지
    않고 관리자 승인(app/api/v1/admin.py의 approve 엔드포인트)이 이 함수를
    개별 항목 단위로 다시 호출한다."""
    published: list[MenuItem] = []
    now = datetime.now(UTC)
    for vp in validated_prices:
        if vp.verdict != PriceVerdict.VALID:
            continue
        item = await publish_one(session, place, vp, now=now)
        published.append(item)
    return published


async def publish_one(
    session: AsyncSession, place: Place, vp: ValidatedPrice, *, now: datetime | None = None
) -> MenuItem:
    now = now or datetime.now(UTC)
    item = MenuItem(
        place_id=place.id,
        name=vp.menu_name,
        price=vp.price,
        source=resolve_source_type(vp.source_type),
        source_url=vp.source_url,
        verified_at=now,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    evidence_parts = [p for p in (vp.source_title, vp.evidence) if p]
    evidence_text = " · ".join(evidence_parts)[:500] if evidence_parts else None
    await sync_menu_offer(session, place, item, price_evidence_text=evidence_text)
    return item
