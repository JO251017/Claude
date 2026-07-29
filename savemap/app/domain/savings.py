from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin
from app.domain.enums import AssetStatus, CertificationConfidence, CertificationMethod


class SavingsCertification(Base, TimestampMixin):
    """실제 인증된 절약 기록. 캐릭터 성장(누적 절약금액)의 유일한 원천."""

    __tablename__ = "savings_certification"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offer.id", ondelete="SET NULL"))
    place_name: Mapped[str] = mapped_column(String(255))
    base_price: Mapped[float] = mapped_column(Numeric(12, 2))
    actual_price: Mapped[float] = mapped_column(Numeric(12, 2))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    method: Mapped[CertificationMethod] = mapped_column(SAEnum(CertificationMethod, name="certification_method"))
    confidence: Mapped[CertificationConfidence] = mapped_column(
        SAEnum(CertificationConfidence, name="certification_confidence")
    )

    __table_args__ = (Index("ix_savings_certification_user_id", "user_id"),)


class SavingsAsset(Base, TimestampMixin):
    """사용자가 보유한 개인 절약 자산(쿠폰/할인권 등). EXCHANGE의 대상."""

    __tablename__ = "savings_asset"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    condition_text: Mapped[str | None] = mapped_column(String(500))
    estimated_value: Mapped[float | None] = mapped_column(Numeric(12, 2))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[AssetStatus] = mapped_column(
        SAEnum(AssetStatus, name="asset_status"), default=AssetStatus.AVAILABLE
    )

    __table_args__ = (Index("ix_savings_asset_owner_user_id", "owner_user_id"),)
