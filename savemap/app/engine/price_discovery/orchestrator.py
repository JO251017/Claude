"""AI Price Discovery Engine — orchestrator(지시서 28-18~28-20, 28-29).

파이프라인 전체를 정해진 순서로만 통과시킨다:
candidate_selector → source_discovery → price_extractor → store_matcher →
price_validator → price_publisher. AI 출력은 이 순서를 다 통과해야만 DB에
반영된다 — 어느 단계든 실패/불확실하면 다음 단계로 넘어가지 않고 그 자리에서
끝난다(28-29 "AI 출력은 절대 DB에 직접 저장하지 않는다").

관리자 검토(manual_review) 흐름은 원본 추출 결과를 별도 테이블에 저장하지
않는다(price_sources/price_evidence를 새로 안 만들기로 한 설계 결정과 같은
이유 — 이번 범위에서 "복잡한 관리자 UI를 새로 만들지 않는다"는 지시서 28-30을
따라 최소 기능만 둔다). 대신 approve는 같은 매장을 강제 모드로 재조사해서
(store 매칭이 REVIEW거나 가격이 이상치였던 항목도 이번엔 그대로 게시) 그
결과를 반영한다 — AI가 store_match 자체를 matched=false로 판단한 경우는
force에서도 절대 우회하지 않는다(그건 "확신이 낮다"가 아니라 "다른 매장"이라는
뜻이라 관리자가 강제로 재실행해도 안전장치를 넘지 않는다)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.place import Place
from app.domain.price_discovery import DiscoveryJobStatus, PriceDiscoveryJob
from app.engine.price_discovery.candidate_selector import get_discovery_candidates
from app.engine.price_discovery.price_extractor import extract_prices
from app.engine.price_discovery.price_publisher import publish_prices
from app.engine.price_discovery.price_validator import PriceVerdict, validate_prices
from app.engine.price_discovery.source_discovery import discover_sources
from app.engine.price_discovery.store_matcher import MatchDecision, decide_match
from app.integrations.gemini import GeminiVisionClient, GroundingUnavailableError

logger = logging.getLogger(__name__)


async def enqueue_candidates(
    session: AsyncSession, *, region: str | None = None, limit: int | None = None
) -> int:
    """가격 없는 매장 중 아직 큐에 없는 곳을 candidate_score 순으로 새 job으로
    등록한다. 반환값: 새로 만든 job 수.

    건당 커밋 + IntegrityError 무시 — "한 번 실행"을 응답 오기 전에 여러 번
    누르는 것처럼 동시에 두 요청이 겹치면, 두 요청 다 같은 매장을 후보로
    조회한 뒤(아직 서로의 INSERT를 못 본 상태) 하나만 커밋에 성공하고 나머지는
    ux_price_discovery_job_active_place 유니크 인덱스에 걸린다 — 이건 버그가
    아니라 큐가 제대로 막고 있다는 신호이므로, 그 매장만 건너뛰고 나머지는
    계속 진행한다(500으로 전체 요청을 죽이지 않는다)."""
    limit = limit or settings.price_discovery_max_jobs_per_run
    candidates = await get_discovery_candidates(session, region=region, limit=limit)
    created = 0
    for c in candidates:
        session.add(PriceDiscoveryJob(place_id=c.place.id, priority=c.score))
        try:
            await session.commit()
            created += 1
        except IntegrityError:
            logger.info("동시 요청으로 이미 큐에 들어간 매장 — 건너뜀 (place_id=%s)", c.place.id)
            await session.rollback()
    return created


async def _process_job(
    session: AsyncSession, job: PriceDiscoveryJob, client: GeminiVisionClient, *, force: bool = False
) -> int:
    """작업 하나를 끝까지 처리하고, 실제로 게시된 가격 건수를 돌려준다(최종
    상태는 job.status에 그대로 반영돼 있으니 호출부가 그걸 읽으면 된다)."""
    job.status = DiscoveryJobStatus.PROCESSING
    job.attempt_count += 1
    job.last_attempted_at = datetime.now(UTC)
    await session.commit()

    place = await session.get(Place, job.place_id)
    if place is None:
        await _give_up(session, job, "PLACE_NOT_FOUND")
        return 0

    try:
        grounding = await discover_sources(place, client)
    except GroundingUnavailableError as exc:
        # 검색 요청 자체가 실패한 경우 — "정말 자료가 없다"(NO_SOURCE_FOUND)와
        # 구분해서 사유를 error_code에 남긴다(예: SEARCH_ERR:HTTP_429,
        # SEARCH_ERR:NO_API_KEY). 32자 컬럼 한도를 넘지 않게 자른다.
        await _retry_or_give_up(session, job, f"SEARCH_ERR:{exc.reason}"[:32])
        return 0
    if grounding is None:
        await _retry_or_give_up(session, job, "NO_SOURCE_FOUND")
        return 0

    extraction = await extract_prices(place, grounding, client)
    if extraction is None:
        await _retry_or_give_up(session, job, "EXTRACTION_FAILED")
        return 0

    decision = decide_match(extraction.store_match)
    if decision == MatchDecision.REJECT:
        # AI 스스로 "이 매장이 아니다"라고 판단한 경우 — force로도 우회하지 않는다.
        job.status = DiscoveryJobStatus.FAILED
        job.error_code = "STORE_NOT_MATCHED"
        job.result_summary = extraction.store_match.reason[:500] or "매장 동일성 확인 실패"
        job.completed_at = datetime.now(UTC)
        await session.commit()
        return 0

    if not extraction.prices:
        job.status = DiscoveryJobStatus.FAILED
        job.error_code = "NO_PRICES_FOUND"
        job.result_summary = "공개 자료에서 가격을 찾지 못했어요"
        job.completed_at = datetime.now(UTC)
        await session.commit()
        return 0

    if decision == MatchDecision.REVIEW and not force:
        job.status = DiscoveryJobStatus.MANUAL_REVIEW
        job.result_summary = (
            f"매장 매칭 확신도 낮음(검토 필요) · 가격 {len(extraction.prices)}건 발견"
        )
        job.completed_at = datetime.now(UTC)
        await session.commit()
        return 0

    validated = validate_prices(extraction.prices)
    to_publish = validated if force else [v for v in validated if v.verdict == PriceVerdict.VALID]
    needs_review = [] if force else [v for v in validated if v.verdict == PriceVerdict.NEEDS_REVIEW]

    published = await publish_prices(session, place, to_publish)

    if needs_review:
        job.status = DiscoveryJobStatus.MANUAL_REVIEW
        job.result_summary = f"자동승인 {len(published)}건 · 검토대기 {len(needs_review)}건(가격 이상치)"
    else:
        job.status = DiscoveryJobStatus.COMPLETED
        job.result_summary = f"가격 {len(published)}건 게시"
    job.completed_at = datetime.now(UTC)
    await session.commit()
    return len(published)


async def _retry_or_give_up(session: AsyncSession, job: PriceDiscoveryJob, error_code: str) -> None:
    """PRICE_DISCOVERY_MAX_RETRY(기본 1)만큼 다음 배치 실행에서 다시 시도할 기회를
    준다 — 무한 재시도는 금지(28-16)."""
    if job.attempt_count > settings.price_discovery_max_retry:
        await _give_up(session, job, error_code)
        return
    job.status = DiscoveryJobStatus.PENDING
    job.error_code = error_code
    await session.commit()


async def _give_up(session: AsyncSession, job: PriceDiscoveryJob, error_code: str) -> None:
    job.status = DiscoveryJobStatus.MANUAL_REVIEW
    job.error_code = error_code
    job.result_summary = "자동 조사가 반복 실패해 수동 확인이 필요해요"
    job.completed_at = datetime.now(UTC)
    await session.commit()


async def run_discovery_batch(session: AsyncSession, *, limit: int | None = None) -> dict:
    """PENDING 큐에서 우선순위 순으로 최대 limit개를 처리한다(28-20/28-21/28-22 —
    Render 무료 플랜엔 상시 worker가 없어 관리자가 이 함수를 반복 호출하는
    구조)."""
    limit = limit or settings.price_discovery_max_jobs_per_run
    client = GeminiVisionClient()

    stmt = (
        select(PriceDiscoveryJob)
        .where(PriceDiscoveryJob.status == DiscoveryJobStatus.PENDING)
        .order_by(PriceDiscoveryJob.priority.desc(), PriceDiscoveryJob.id)
        .limit(limit)
    )
    jobs = list((await session.execute(stmt)).scalars().all())

    prices_found = 0
    completed = 0
    manual_review = 0
    failed = 0
    for job in jobs:
        try:
            prices_found += await _process_job(session, job, client)
        except Exception as exc:  # noqa: BLE001 - 작업 하나 실패가 나머지를 막으면 안 됨
            logger.warning("가격 발견 작업 실패 (job_id=%s): %s", job.id, exc)
            await session.rollback()
            job.status = DiscoveryJobStatus.FAILED
            job.error_code = "UNEXPECTED_ERROR"
            job.result_summary = str(exc)[:200]
            job.completed_at = datetime.now(UTC)
            await session.commit()

        if job.status == DiscoveryJobStatus.COMPLETED:
            completed += 1
        elif job.status == DiscoveryJobStatus.MANUAL_REVIEW:
            manual_review += 1
        elif job.status == DiscoveryJobStatus.FAILED:
            failed += 1
        # PENDING(재시도 대기)은 세 카운트 어디에도 안 들어간다 — 다음 배치 실행 대상.

    return {
        "jobs_picked_up": len(jobs),
        "jobs_completed": completed,
        "jobs_manual_review": manual_review,
        "jobs_failed": failed,
        "prices_found": prices_found,
    }


async def approve_job(session: AsyncSession, job: PriceDiscoveryJob) -> int:
    """manual_review 작업을 강제 모드로 재실행해 게시한다(force=True) — 매장 매칭
    자체가 AI 판단으로 거절된 작업(FAILED/STORE_NOT_MATCHED)은 여기서 승인
    대상이 아니다(호출부가 상태를 미리 확인). 반환값: 이번에 게시된 가격 건수."""
    client = GeminiVisionClient()
    return await _process_job(session, job, client, force=True)


async def reject_job(session: AsyncSession, job: PriceDiscoveryJob) -> None:
    job.status = DiscoveryJobStatus.FAILED
    job.error_code = "REJECTED_BY_ADMIN"
    job.completed_at = datetime.now(UTC)
    await session.commit()
