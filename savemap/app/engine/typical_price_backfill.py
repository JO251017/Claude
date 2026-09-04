"""절약 기회 점수 활성화(2026-09-01, §17~18)의 유일한 구제 경로 — 재동기화가
근거를 얻으려면 MenuItem.ai_typical_price가 채워져 있어야 한다. 이웃 매장도
없고(region) 참가격 품목도 아닌(gov) 메뉴는 이게 없으면 절약 기회 점수 자체가
안 뜬다(app/engine/price_comparison.py:compare_menu_item의 벤치마크 사다리 참고).

app/engine/offer_blurb_backfill.py(안건 D)와 완전히 같은 패턴의 관리자 배치다:
Render 무료 플랜에 상시 worker가 없어 admin-maintenance.html에서 반복 호출해야
한다. 키셋 페이지네이션(MenuItem.id 기준), dry_run 지원, 행 하나 실패가
나머지를 막지 않는 try/except까지 같은 관례.

지역 세분화(§26~27): 같은 메뉴명이라도 지역마다 통상가가 다를 수 있어
(normalized_name, region) 조합을 캐시 키로 쓴다 — 배치 시작 시 기존
ai_typical_price 값들을 이 조합으로 미리 로드해, 같은 조합이면 API 호출 없이
복사한다(§42 "동일 benchmark 반복 생성 금지"). region을 못 알아내면(주소가
시도로 시작하지 않는 등) region=None으로 취급해 예전처럼 전국 단일 추정을
캐시/재사용한다."""

import logging
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.menu_name import normalize_menu_name
from app.integrations.gemini import GeminiVisionClient
from app.sources.public_api.dine_out_price import region_from_address

logger = logging.getLogger(__name__)

# 한 번의 API 호출에 묶어 보낼 (메뉴명, 지역) 조합 수. 너무 크게 잡으면 응답이
# 길어져 잘리거나 정렬이 어긋날 위험이 커지고, 너무 작으면 묶는 의미가 없다.
_BATCH_SIZE = 40


class _CacheKey(NamedTuple):
    normalized_name: str
    region: str | None


async def _load_existing_estimates(session: AsyncSession) -> dict[_CacheKey, float]:
    """이미 추정치가 있는 메뉴들의 (normalized_name, region) → price 맵을 미리
    한 번에 로드한다 — 배치 안에서 같은 조합을 API로 다시 물어보지 않기 위함."""
    rows = (
        await session.execute(
            select(MenuItem.normalized_name, Place.address, MenuItem.ai_typical_price)
            .join(Place, MenuItem.place_id == Place.id)
            .where(MenuItem.ai_typical_price.is_not(None))
        )
    ).all()
    cache: dict[_CacheKey, float] = {}
    for normalized_name, address, price in rows:
        key = _CacheKey(normalized_name, region_from_address(address))
        cache.setdefault(key, float(price))
    return cache


async def backfill_typical_prices(
    session: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 100,
    dry_run: bool = False,
    client: GeminiVisionClient | None = None,
) -> dict:
    """MenuItem.id >= offset부터, ai_typical_price가 아직 없는 메뉴 최대 limit개에
    통상가를 채운다. dry_run=True면 채우기만 하고 저장은 안 한다(끝에 롤백)."""
    client = client or GeminiVisionClient()
    stmt = (
        select(MenuItem, Place)
        .join(Place, MenuItem.place_id == Place.id)
        .where(MenuItem.id >= offset, MenuItem.ai_typical_price.is_(None))
        .order_by(MenuItem.id)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        return {
            "offset": offset, "dry_run": dry_run,
            "scanned": 0, "estimated": 0, "reused_from_cache": 0, "failed": 0,
            "next_offset": offset, "done": True,
        }

    cache = await _load_existing_estimates(session)

    # 이번 페이지에서 각 행이 어떤 (메뉴명, 지역) 조합인지 먼저 정리한다.
    keyed_rows = [
        (item, _CacheKey(item.normalized_name or normalize_menu_name(item.name),
                         region_from_address(place.address)))
        for item, place in rows
    ]

    # 캐시에 없는 조합만 모아서 한 번에 묶어 물어본다(2026-09-04). 예전엔 행마다
    # API를 한 번씩 불렀는데, 고유 메뉴명이 2,881개라 무료 한도로는 며칠이
    # 걸렸다. 같은 조합은 여기서 이미 한 번으로 합쳐지고, 남은 것들도
    # _BATCH_SIZE개씩 묶여서 호출 수가 수십분의 1로 준다.
    pending = [key for _, key in keyed_rows if key not in cache]
    unique_pending = list(dict.fromkeys(pending))  # 순서 유지 중복 제거

    estimated = 0
    failed_keys: set[_CacheKey] = set()
    for start in range(0, len(unique_pending), _BATCH_SIZE):
        chunk = unique_pending[start : start + _BATCH_SIZE]
        try:
            prices = await client.estimate_typical_prices_batch(
                [(key.normalized_name, key.region) for key in chunk]
            )
        except Exception as exc:  # noqa: BLE001 - 한 묶음 실패가 나머지 묶음을 막으면 안 됨
            logger.warning("통상가 배치 추정 실패 (%d건): %s", len(chunk), exc)
            failed_keys.update(chunk)
            continue
        for i, key in enumerate(chunk):
            price = prices.get(i)
            if price is None:
                # 응답에 없거나 null이면 추정 실패로 둔다 — 지어내지 않는다.
                failed_keys.add(key)
                continue
            cache[key] = price
            estimated += 1

    reused = 0
    failed = 0
    for item, key in keyed_rows:
        price = cache.get(key)
        if price is None:
            failed += 1
            continue
        if key not in failed_keys and key in cache:
            reused += 1
        if not dry_run:
            item.ai_typical_price = price
    # estimated는 "이번에 새로 추정한 고유 조합 수"라 위에서 이미 셌다 —
    # reused에서 그만큼 빼야 "캐시 재사용" 숫자가 실제 의미를 갖는다.
    reused = max(reused - estimated, 0)

    item_ids = [item.id for item, _ in rows]
    if dry_run:
        await session.rollback()
    else:
        await session.commit()

    next_offset = item_ids[-1] + 1
    return {
        "offset": offset, "dry_run": dry_run,
        "scanned": len(rows), "estimated": estimated,
        "reused_from_cache": reused, "failed": failed,
        "next_offset": next_offset, "done": len(rows) < limit,
    }
