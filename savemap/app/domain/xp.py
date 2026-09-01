from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin
from app.domain.enums import XpReason


class XpLedger(Base, TimestampMixin):
    __tablename__ = "xp_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[XpReason] = mapped_column(SAEnum(XpReason, name="xp_reason"))
    # 성장 이벤트 기록(2026-09-01, "행동을 이벤트로 기록") — 새 이벤트 테이블을
    # 따로 만들지 않는다. xp_ledger가 이미 user_id/reason(=event_type)/created_at을
    # 갖고 있어 place_id 하나만 추가하면 §33이 요구하는 형태와 같아진다. 맥락이
    # 없는 기존 3개 호출부(certification/community_menu/user_verification)는
    # place_id를 넘기지 않아도 되도록 기본값 None.
    place_id: Mapped[int | None] = mapped_column(ForeignKey("place.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_xp_ledger_user_id", "user_id"),)
