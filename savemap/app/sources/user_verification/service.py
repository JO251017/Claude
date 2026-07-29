from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Verdict, XpReason
from app.domain.offer_verification import OfferVerification
from app.domain.trust import TrustScore
from app.domain.verification import Verification
from app.gamification.service import award_xp
from app.sources.user_verification.scoring import recompute_trust


async def submit_verification(
    session: AsyncSession, report_id: int, user_id: str, verdict: Verdict, weight: float = 1.0
) -> float:
    session.add(
        Verification(report_id=report_id, user_id=user_id, verdict=verdict, weight=weight)
    )
    await session.flush()

    rows = (
        await session.execute(
            select(Verification.verdict, Verification.weight).where(
                Verification.report_id == report_id
            )
        )
    ).all()
    score = recompute_trust([(r[0], float(r[1])) for r in rows])

    existing = (
        await session.execute(
            select(TrustScore).where(
                TrustScore.subject_type == "report", TrustScore.subject_id == report_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(TrustScore(subject_type="report", subject_id=report_id, score=score))
    else:
        existing.score = score

    await award_xp(session, user_id, XpReason.FIELD_VERIFICATION)
    await session.commit()
    return score


async def submit_offer_verification(
    session: AsyncSession, offer_id: int, user_id: str, verdict: Verdict
) -> tuple[float, int, datetime]:
    """MAP 카드(오퍼) 단위 검증. "아직 있어요/없어졌어요"에 대응한다."""
    session.add(OfferVerification(offer_id=offer_id, user_id=user_id, verdict=verdict))
    await session.flush()

    rows = (
        await session.execute(
            select(OfferVerification.verdict).where(OfferVerification.offer_id == offer_id)
        )
    ).all()
    score = recompute_trust([(r[0], 1.0) for r in rows])

    existing = (
        await session.execute(
            select(TrustScore).where(
                TrustScore.subject_type == "offer", TrustScore.subject_id == offer_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(TrustScore(subject_type="offer", subject_id=offer_id, score=score))
    else:
        existing.score = score

    await award_xp(session, user_id, XpReason.FIELD_VERIFICATION)
    await session.commit()

    count, last_at = (
        await session.execute(
            select(func.count(), func.max(OfferVerification.created_at)).where(
                OfferVerification.offer_id == offer_id
            )
        )
    ).one()
    return score, count, last_at


async def get_offer_trust_map(
    session: AsyncSession, offer_ids: list[int]
) -> dict[int, tuple[float, int, datetime | None]]:
    """검색 결과에 실제 신뢰도/검증 횟수/마지막 확인 시각을 붙이기 위한 배치 조회."""
    if not offer_ids:
        return {}

    trust_rows = (
        await session.execute(
            select(TrustScore.subject_id, TrustScore.score).where(
                TrustScore.subject_type == "offer", TrustScore.subject_id.in_(offer_ids)
            )
        )
    ).all()
    trust_map = {r[0]: float(r[1]) for r in trust_rows}

    agg_rows = (
        await session.execute(
            select(
                OfferVerification.offer_id,
                func.count(),
                func.max(OfferVerification.created_at),
            )
            .where(OfferVerification.offer_id.in_(offer_ids))
            .group_by(OfferVerification.offer_id)
        )
    ).all()
    agg_map = {r[0]: (r[1], r[2]) for r in agg_rows}

    return {
        offer_id: (trust_map.get(offer_id, 0.5), *agg_map.get(offer_id, (0, None)))
        for offer_id in offer_ids
    }
