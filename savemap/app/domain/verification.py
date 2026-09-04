from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin
from app.domain.enums import Verdict


class Verification(Base, TimestampMixin):
    __tablename__ = "verification"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("user_report.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[Verdict] = mapped_column(SAEnum(Verdict, name="verdict_type"))
    weight: Mapped[float] = mapped_column(Numeric(5, 4), default=1.0)

    __table_args__ = (Index("ix_verification_report_id", "report_id"),)
