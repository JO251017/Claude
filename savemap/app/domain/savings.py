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
    # offer가 나중에 삭제/변경돼도 "이 매장이 몇 번 식사 인증됐는지" 집계가 끊기지 않도록
    # place_id를 직접 들고 있는다 (offer_id만으로는 SET NULL 시 매장 연결이 끊김).
    place_id: Mapped[int | None] = mapped_column(ForeignKey("place.id", ondelete="SET NULL"))
    place_name: Mapped[str] = mapped_column(String(255))
    base_price: Mapped[float] = mapped_column(Numeric(12, 2))
    actual_price: Mapped[float] = mapped_column(Numeric(12, 2))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    method: Mapped[CertificationMethod] = mapped_column(SAEnum(CertificationMethod, name="certification_method"))
    confidence: Mapped[CertificationConfidence] = mapped_column(
        SAEnum(CertificationConfidence, name="certification_confidence")
    )

    __table_args__ = (
        Index("ix_savings_certification_user_id", "user_id"),
        Index("ix_savings_certification_place_id", "place_id"),
    )


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
    # EXCHANGE 재도입(SaveMap 구조 재설계 제안서 §07, 2026-08-13) — 오퍼 상세
    # "저장하기"로 만든 자산과 기존 자유입력 자산이 같은 테이블에 공존하므로 셋 다
    # nullable. offer_id만으로는 오퍼가 삭제/변경돼도 매장 연결이 끊기므로
    # place_id/place_name을 SavingsCertification과 같은 패턴으로 같이 들고 있는다.
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offer.id", ondelete="SET NULL"))
    place_id: Mapped[int | None] = mapped_column(ForeignKey("place.id", ondelete="SET NULL"))
    place_name: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        Index("ix_savings_asset_owner_user_id", "owner_user_id"),
        Index("ix_savings_asset_place_id", "place_id"),
    )
