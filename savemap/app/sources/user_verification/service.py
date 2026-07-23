from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Verdict, XpReason
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
