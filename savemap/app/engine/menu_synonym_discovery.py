"""메뉴명 동의어 AI 발견(2026-09-04) — app/engine/menu_name.py의 _SYNONYMS를
사람이 직접 눈으로 훑어서 채웠던(23쌍) 절차를, AI로 후보를 넓게 뽑고 사람이
승인하는 두 단계로 나눈다.

이 배치가 하는 일은 딱 여기까지다: (1) 아직 후보로 안 나온 조합의 메뉴명을
_BATCH_SIZE개씩 묶어 AI에게 "표기만 다른 쌍"을 물어보고 (2) 결과를
menu_synonym_candidate 테이블에 저장한다. 실제 정규화 규칙(_SYNONYMS)에는
아무것도 자동 반영하지 않는다 — 그건 사람이 후보를 검토해서 별도로 커밋하는
몫이다(잘못 합치면 값이 다른 메뉴끼리 비교해 없는 절약률을 만들어낸다).

app/engine/offer_blurb_backfill.py·typical_price_backfill.py와 같은 관리자
배치 패턴: Render 무료 플랜에 상시 worker가 없어 admin-maintenance.html에서
반복 호출해야 한다. 키셋 페이지네이션, dry_run 지원, 한 묶음 실패가 나머지를
막지 않는 fail-soft까지 같은 관례."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.menu_item import MenuItem
from app.domain.menu_synonym import MenuSynonymCandidate
from app.engine.menu_name import get_known_synonym_pairs
from app.integrations.gemini import GeminiVisionClient

logger = logging.getLogger(__name__)

# 한 번의 API 호출에 묶어 보낼 메뉴명 수. 짧은 단어 목록이라 통상가 배치(40개)
# 보다 조금 더 크게 잡아도 안전하다.
_BATCH_SIZE = 60

# 매장 1곳뿐인 이름은 애초에 비교 상대가 없어 동의어로 묶여도 실측 비교
# 커버리지에 도움이 안 된다 — 후보 탐색 대상에서 아예 제외해 호출 수를 줄인다.
_MIN_PLACES_TO_CONSIDER = 2


async def _load_candidate_names(session: AsyncSession) -> list[str]:
    """탐색 대상 이름 목록 — 매장 2곳 이상인 정규화 이름 중, 이미 _SYNONYMS에
    등록됐거나(코드에 이미 반영됨) 이미 후보 테이블에 있는 쌍은 다시 안
    묻는다. 매장 수 많은 순으로 봐야 같은 API 호출로 더 큰 효과를 먼저
    건진다."""
    rows = (
        await session.execute(
            select(MenuItem.normalized_name, func.count(func.distinct(MenuItem.place_id)))
            .group_by(MenuItem.normalized_name)
            .having(func.count(func.distinct(MenuItem.place_id)) >= _MIN_PLACES_TO_CONSIDER)
            .order_by(func.count(func.distinct(MenuItem.place_id)).desc())
        )
    ).all()
    known = get_known_synonym_pairs()  # {variant, canonical} 문자열 전부
    return [name for name, _ in rows if name and name not in known]


async def _load_existing_candidate_pairs(session: AsyncSession) -> set[tuple[str, str]]:
    rows = (
        await session.execute(select(MenuSynonymCandidate.variant, MenuSynonymCandidate.canonical))
    ).all()
    return {(v, c) for v, c in rows}


async def discover_menu_synonym_candidates(
    session: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 300,
    dry_run: bool = False,
    client: GeminiVisionClient | None = None,
) -> dict:
    """이름 목록에서 offset부터 limit개를 _BATCH_SIZE씩 나눠 AI에게 묻고,
    새로 나온 후보만 저장한다. offset/limit은 "이름 개수" 기준이라, 다음 호출
    시 next_offset을 그대로 넘기면 이어서 진행된다."""
    client = client or GeminiVisionClient()
    all_names = await _load_candidate_names(session)
    page = all_names[offset : offset + limit]

    if not page:
        return {
            "offset": offset, "dry_run": dry_run,
            "scanned": 0, "found": 0, "saved": 0,
            "next_offset": offset, "done": True,
        }

    existing_pairs = await _load_existing_candidate_pairs(session)
    found = 0
    saved = 0

    for start in range(0, len(page), _BATCH_SIZE):
        chunk = page[start : start + _BATCH_SIZE]
        try:
            pairs = await client.suggest_menu_synonyms_batch(chunk)
        except Exception as exc:  # noqa: BLE001 - 한 묶음 실패가 나머지 묶음을 막으면 안 됨
            logger.warning("동의어 후보 탐색 실패 (%d건): %s", len(chunk), exc)
            continue
        found += len(pairs)
        for variant, canonical, reason in pairs:
            if variant == canonical:
                continue
            key = (variant, canonical)
            if key in existing_pairs:
                continue
            existing_pairs.add(key)
            if not dry_run:
                session.add(
                    MenuSynonymCandidate(
                        variant=variant,
                        canonical=canonical,
                        reason=reason,
                        variant_places=None,
                        canonical_places=None,
                    )
                )
            saved += 1

    if dry_run:
        await session.rollback()
    else:
        await session.commit()

    next_offset = offset + len(page)
    return {
        "offset": offset, "dry_run": dry_run,
        "scanned": len(page), "found": found, "saved": saved,
        "next_offset": next_offset, "done": next_offset >= len(all_names),
    }
