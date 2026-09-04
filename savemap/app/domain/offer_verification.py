from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin
from app.domain.enums import Verdict


class OfferVerification(Base, TimestampMixin):
    """MAP 카드(오퍼) 단위 "아직 있어요/없어졌어요" 검증. user_report 대상 Verification과 별개다."""

    __tablename__ = "offer_verification"

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offer.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[Verdict] = mapped_column(SAEnum(Verdict, name="verdict_type"))

    __table_args__ = (Index("ix_offer_verification_offer_id", "offer_id"),)
