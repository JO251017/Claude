"""이미 만들어진 Offer를 다시 sync_menu_offer에 태워 최신 벤치마크로 갱신한다.

절약 계산(price_comparison.compare_menu_item)은 메뉴가 적재/갱신될 때 딱 한 번만
돌고 결과가 Offer 컬럼에 그대로 굳는다(app/engine/offer_sync.py). 나중에 주변에
매장이 더 생기거나, 참가격 통계·프랜차이즈 가격처럼 새 벤치마크 소스가 채워져도
이미 만들어진 오퍼는 재계산 전까지 계속 옛날 benchmark_source/절약률을 보여준다 —
"표본이 쌓이면 자동 승격된다"는 이전 주석은 이 배치가 돌 때만 참이 된다.

착한가격업소/프랜차이즈 어댑터와 같은 관례를 따른다: MenuItem.id 키셋 페이지네이션
(OFFSET 스캔 비용·동시 삽입 시 행 누락을 피함), 행 하나 실패가 나머지를 막지 않는
try/except, 응답에 실제로 뭐가 바뀌었는지(전이 행렬) 노출해서 배포 전 dry_run으로
영향 범위를 먼저 잴 수 있게 한다.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SourceType
from app.domain.menu_item import MenuItem
from app.domain.offer import Offer
from app.domain.place import Place
from app.domain.price_history import PriceHistory
from app.engine.offer_sync import sync_menu_offer

logger = logging.getLogger(__name__)

# 건당 커밋(느리지만 부분 실패해도 그때까지는 안전)과 전건 일괄 커밋(빠르지만 실패
# 시 전량 롤백) 사이의 절충 — 이 정도 묶음이면 실패해도 되돌리는 범위가 작다.
COMMIT_CHUNK = 50


async def resync_offers(
    session: AsyncSession,
    *,
    region: str | None = None,
    offset: int = 0,
    limit: int = 500,
    source: SourceType | None = None,
    dry_run: bool = False,
) -> dict:
    """MenuItem.id >= offset부터 limit개를 훑어 각각의 오퍼를 재계산한다.

    place.geom이 없는 매장(좌표 미확보)은 sync_menu_offer가 to_shape에서 바로
    터지므로 건너뛰고 skipped_no_geom으로 센다. dry_run=True면 계산은 다 하되 끝에
    롤백해서 실제로는 아무것도 안 바뀐다 — 배포 전에 benchmark_transitions만 미리
    보고 영향 범위를 잴 때 쓴다."""
    stmt = (
        select(MenuItem, Place)
        .join(Place, MenuItem.place_id == Place.id)
        .where(MenuItem.id >= offset)
    )
    if region:
        stmt = stmt.where(Place.address.contains(region))
    if source:
        stmt = stmt.where(MenuItem.source == source)
    rows = (await session.execute(stmt.order_by(MenuItem.id).limit(limit))).all()

    if not rows:
        return {
            "region": region, "offset": offset, "dry_run": dry_run,
            "scanned": 0, "resynced": 0, "skipped_no_geom": 0, "failed": [],
            "changed": 0, "benchmark_transitions": {}, "source_after": {},
            "next_offset": offset, "done": True,
        }

    menu_item_ids = [item.id for item, _ in rows]
    existing_offers = {
        offer.menu_item_id: offer
        for offer in (
            await session.execute(select(Offer).where(Offer.menu_item_id.in_(menu_item_ids)))
        ).scalars().all()
    }
    # sync_menu_offer가 이제 가격 이력(price_history)도 남기는데, 그 판단에 "이
    # 메뉴의 현재 이력 행"이 필요하다 — existing_offers와 같은 이유로 IN절 한 번에
    # 미리 조회해 넘긴다(안 그러면 이 배치가 없앤 건당 SELECT가 여기서 되살아난다).
    current_price_history = {
        row.menu_item_id: row
        for row in (
            await session.execute(
                select(PriceHistory).where(
                    PriceHistory.menu_item_id.in_(menu_item_ids), PriceHistory.is_current.is_(True)
                )
            )
        ).scalars().all()
    }

    resynced = 0
    skipped_no_geom = 0
    changed = 0
    failed: list[dict] = []
    transitions: dict[str, int] = {}
    source_after: dict[str, int] = {}

    def _label(v: str | None) -> str:
        return v or "none"

    for i, (item, place) in enumerate(rows):
        if place.geom is None:
            skipped_no_geom += 1
            continue

        existing = existing_offers.get(item.id)
        before = existing.benchmark_source if existing else None
        try:
            cmp = await sync_menu_offer(
                session,
                place,
                item,
                commit=False,
                existing_offer=existing,
                current_price_history=current_price_history.get(item.id),
            )
        except Exception as exc:  # noqa: BLE001 - 행 하나 실패가 나머지 수천 건을 막으면 안 됨
            logger.warning("오퍼 재동기화 실패 (menu_item_id=%s): %s", item.id, exc)
            await session.rollback()
            failed.append({"menu_item_id": item.id, "reason": str(exc)[:200]})
            continue

        resynced += 1
        after = cmp.benchmark_source
        if after != before:
            changed += 1
        transitions[f"{_label(before)}->{_label(after)}"] = (
            transitions.get(f"{_label(before)}->{_label(after)}", 0) + 1
        )
        source_after[_label(after)] = source_after.get(_label(after), 0) + 1

        if (i + 1) % COMMIT_CHUNK == 0:
            await session.commit()

    if dry_run:
        await session.rollback()
    else:
        await session.commit()

    next_offset = menu_item_ids[-1] + 1
    return {
        "region": region,
        "offset": offset,
        "dry_run": dry_run,
        "scanned": len(rows),
        "resynced": resynced,
        "skipped_no_geom": skipped_no_geom,
        "failed": failed,
        "changed": changed,
        "benchmark_transitions": transitions,
        "source_after": source_after,
        "next_offset": next_offset,
        "done": len(rows) < limit,
    }
