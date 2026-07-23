from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin
from app.domain.enums import XpReason


class XpLedger(Base, TimestampMixin):
    __tablename__ = "xp_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[XpReason] = mapped_column(SAEnum(XpReason, name="xp_reason"))

    __table_args__ = (Index("ix_xp_ledger_user_id", "user_id"),)
