import asyncio

from sqlalchemy import select

from app.core.db import SessionLocal
from app.domain.enums import ReportStatus, Verdict
from app.domain.report import UserReport
from app.domain.trust import TrustScore
from app.domain.xp import XpLedger
from app.sources.user_verification.service import submit_verification


async def main():
    async with SessionLocal() as session:
        report = UserReport(
            user_id="reporter_1", image_url="http://example.com/x.jpg", status=ReportStatus.PENDING
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        print("report created id=", report.id)

    async with SessionLocal() as session:
        score1 = await submit_verification(session, report.id, "verifier_1", Verdict.AVAILABLE)
        print("after 1 AVAILABLE vote, trust_score=", score1)
        assert score1 == 1.0, f"expected 1.0, got {score1}"

    async with SessionLocal() as session:
        score2 = await submit_verification(session, report.id, "verifier_2", Verdict.SOLD_OUT)
        print("after 1 AVAILABLE + 1 SOLD_OUT vote, trust_score=", score2)
        assert score2 == 0.5, f"expected 0.5, got {score2}"

    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(TrustScore).where(
                    TrustScore.subject_type == "report", TrustScore.subject_id == report.id
                )
            )
        ).scalar_one()
        print("trust_score row in DB:", row.score)
        assert float(row.score) == 0.5

        xp_rows = (
            await session.execute(
                select(XpLedger).where(XpLedger.user_id.in_(["verifier_1", "verifier_2"]))
            )
        ).scalars().all()
        for xp in xp_rows:
            print("xp awarded:", xp.user_id, xp.delta, xp.reason)
        assert len(xp_rows) == 2
        assert all(xp.delta == 5 for xp in xp_rows)

    print("ALL OK")


asyncio.run(main())
