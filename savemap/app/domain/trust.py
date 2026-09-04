from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base


class TrustScore(Base):
    __tablename__ = "trust_score"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[int] = mapped_column()
    score: Mapped[float] = mapped_column(Numeric(5, 4), default=0.5)
    recomputed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("subject_type", "subject_id", name="uq_trust_subject"),)
