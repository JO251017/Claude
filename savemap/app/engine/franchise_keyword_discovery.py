"""프랜차이즈 매칭 키워드 AI 발견(2026-09-04) — menu_synonym_discovery.py와
완전히 같은 두 단계 구조를 브랜드 매칭에 적용한다: (1) 아직 제안이 없는
브랜드를 _BATCH_SIZE개씩 묶어 AI에게 "간판/지도앱에서 흔히 쓰이는 표기 변형"을
물어보고 (2) 결과를 franchise_brand.suggested_match_keywords 컬럼에 저장한다.

실제 매칭 규칙(match_keywords, app/sources/public_api/franchise_price.py의
matches_brand)에는 아무것도 자동 반영하지 않는다 — 브랜드 매칭을 잘못 넓히면
엉뚱한 매장에 그 브랜드의 공식 가격이 그대로 붙어버린다. 사람이 제안을
검토해서 match_keywords로 직접 옮겨야만 실제로 적용된다.

app/engine/offer_blurb_backfill.py·typical_price_backfill.py·
menu_synonym_discovery.py와 같은 관리자 배치 패턴: Render 무료 플랜에 상시
worker가 없어 admin-maintenance.html에서 반복 호출해야 한다. 키셋
페이지네이션, dry_run 지원, 한 묶음 실패가 나머지를 막지 않는 fail-soft까지
같은 관례."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.franchise import FranchiseBrand
from app.integrations.gemini import GeminiVisionClient

logger = logging.getLogger(__name__)

# 한 번의 API 호출에 묶어 보낼 브랜드 수. 브랜드 수 자체가 적어(2026-09-04
# 기준 4개) 사실상 배치가 나뉘지 않지만, 브랜드가 늘어나도 안전하도록
# 다른 배치(통상가 40, 동의어 60)와 비슷한 규모로 잡는다.
_BATCH_SIZE = 50


async def _load_candidate_brands(session: AsyncSession) -> list[FranchiseBrand]:
    """제안이 아직 없는 브랜드만 대상으로 한다 — 이미 제안이 쌓여 있으면
    사람이 검토할 때까지 같은 브랜드를 다시 묻지 않는다(호출 수 절약)."""
    rows = (
        await session.execute(
            select(FranchiseBrand)
            .where(FranchiseBrand.suggested_match_keywords.is_(None))
            .order_by(FranchiseBrand.id)
        )
    ).scalars().all()
    return list(rows)


async def discover_franchise_keywords(
    session: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 100,
    dry_run: bool = False,
    client: GeminiVisionClient | None = None,
) -> dict:
    """브랜드 목록에서 offset부터 limit개를 _BATCH_SIZE씩 나눠 AI에게 묻고,
    제안이 나온 브랜드에 suggested_match_keywords를 채운다. offset/limit은
    "제안 없는 브랜드 개수" 기준이라, 다음 호출 시 next_offset을 그대로
    넘기면 이어서 진행된다."""
    client = client or GeminiVisionClient()
    all_brands = await _load_candidate_brands(session)
    page = all_brands[offset : offset + limit]

    if not page:
        return {
            "offset": offset, "dry_run": dry_run,
            "scanned": 0, "suggested": 0,
            "next_offset": offset, "done": True,
        }

    scanned = 0
    suggested = 0

    for start in range(0, len(page), _BATCH_SIZE):
        chunk = page[start : start + _BATCH_SIZE]
        scanned += len(chunk)
        pairs = [(b.name, b.match_keywords) for b in chunk]
        try:
            result = await client.suggest_franchise_keywords_batch(pairs)
        except Exception as exc:  # noqa: BLE001 - 한 묶음 실패가 나머지 묶음을 막으면 안 됨
            logger.warning("프랜차이즈 키워드 제안 탐색 실패 (%d건): %s", len(chunk), exc)
            continue
        for idx, keywords in result.items():
            brand = chunk[idx]
            if not dry_run:
                brand.suggested_match_keywords = "|".join(keywords)
            suggested += 1

    if dry_run:
        await session.rollback()
    else:
        await session.commit()

    next_offset = offset + len(page)
    return {
        "offset": offset, "dry_run": dry_run,
        "scanned": scanned, "suggested": suggested,
        "next_offset": next_offset, "done": next_offset >= len(all_brands),
    }
