"""AI 활용 확대 안건 D(2026-08-31) — 매장 카드 한 줄 소개(Offer.ai_one_line)를
관리자 배치로 미리 생성해 캐시한다.

app/engine/offer_resync.py와 똑같은 이유로 배치 형태다: Render 무료 플랜에
상시 worker가 없어 관리자가 admin-maintenance.html에서 반복 호출해야 한다.
키셋 페이지네이션(Offer.id 기준), dry_run 지원, 행 하나 실패가 나머지를
막지 않는 try/except까지 같은 패턴을 그대로 따른다.

절약을 아직 주장하지 않는 오퍼(store_discount<=0)는 소개할 만한 사실이
마땅치 않아 건너뛴다 — 그런 오퍼는 이미 savings_report.py의 결정론적
"아직 데이터 부족" 문구가 정직하게 그 상태를 그대로 말해준다."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.ai_text_guard import has_unapproved_numbers
from app.integrations.gemini import GeminiVisionClient

logger = logging.getLogger(__name__)

_BENCHMARK_LABELS = {
    "region": "주변 매장 실측가",
    "gov": "한국소비자원 참가격 시도 평균가",
    "ai": "AI 추정 통상가",
}

# ai_one_line 컬럼 한도(200자)보다 훨씬 짧게 자른다 — 프롬프트가 이미 40자
# 이내를 요구하지만, 모델이 어기는 경우까지 대비한 안전판.
_MAX_BLURB_LEN = 120


def _facts_for_offer(offer: Offer, place: Place) -> tuple[dict[str, str], set[str]]:
    """generate_offer_blurb에 줄 사실 목록과, 그 안에 실제로 등장한 숫자(허용
    목록)를 함께 만든다. 정확한 절약률(%)은 payment_benefits까지 반영해야 검색
    응답 숫자와 100% 일치하는데 이 배치는 그 테이블을 조인하지 않으므로, 어긋날
    수 있는 정확한 숫자는 아예 사실 목록에 안 넣는다(정성적 사실만 준다) — 카드에
    이미 정확한 %가 따로 표시되니 문장이 그걸 다시 반복할 필요도 없다."""
    facts: dict[str, str] = {"업종": place.category_name or offer.category.value}
    allowed: set[str] = set()

    if offer.benchmark_source:
        facts["가격 비교 기준"] = _BENCHMARK_LABELS.get(offer.benchmark_source, offer.benchmark_source)
        facts["비교 결과"] = "이 비교 기준보다 저렴함"

    if offer.benchmark_source == "region" and offer.benchmark_sample_count:
        n = str(offer.benchmark_sample_count)
        facts["비교한 주변 매장 수"] = f"{n}곳"
        allowed.add(n)

    return facts, allowed


async def backfill_offer_blurbs(
    session: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 100,
    dry_run: bool = False,
    client: GeminiVisionClient | None = None,
) -> dict:
    """Offer.id >= offset부터, ai_one_line이 아직 없고 절약을 주장하는(store_discount>0)
    오퍼 최대 limit개에 대해 한 줄 소개를 생성한다. dry_run=True면 생성만 하고
    저장은 안 한다(끝에 롤백)."""
    client = client or GeminiVisionClient()
    stmt = (
        select(Offer, Place)
        .join(Place, Offer.place_id == Place.id)
        .where(
            Offer.id >= offset,
            Offer.ai_one_line.is_(None),
            Offer.store_discount > 0,
            Offer.base_price > 0,
        )
        .order_by(Offer.id)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        return {
            "offset": offset, "dry_run": dry_run,
            "scanned": 0, "generated": 0, "rejected_hallucination": 0, "failed": 0,
            "next_offset": offset, "done": True,
        }

    generated = 0
    rejected = 0
    failed = 0
    now = datetime.now(UTC)

    for offer, place in rows:
        facts, allowed = _facts_for_offer(offer, place)
        try:
            text = await client.generate_offer_blurb(facts)
        except Exception as exc:  # noqa: BLE001 - 행 하나 실패가 나머지 수십 건을 막으면 안 됨
            logger.warning("오퍼 한줄소개 생성 실패 (offer_id=%s): %s", offer.id, exc)
            failed += 1
            continue

        if text is None:
            failed += 1
            continue
        if has_unapproved_numbers(text, allowed):
            logger.warning(
                "오퍼 한줄소개 숫자 환각 감지, 버림 (offer_id=%s): %r", offer.id, text
            )
            rejected += 1
            continue

        if not dry_run:
            offer.ai_one_line = text[:_MAX_BLURB_LEN]
            offer.ai_one_line_generated_at = now
        generated += 1

    offer_ids = [offer.id for offer, _ in rows]
    if dry_run:
        await session.rollback()
    else:
        await session.commit()

    next_offset = offer_ids[-1] + 1
    return {
        "offset": offset, "dry_run": dry_run,
        "scanned": len(rows), "generated": generated,
        "rejected_hallucination": rejected, "failed": failed,
        "next_offset": next_offset, "done": len(rows) < limit,
    }
