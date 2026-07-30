from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.base import Base, TimestampMixin
from app.domain.enums import Category, Layer, PaymentMethodType, SourceType


class Offer(Base, TimestampMixin):
    __tablename__ = "offer"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    source: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type"))
    layer: Mapped[Layer] = mapped_column(SAEnum(Layer, name="layer_type"))
    category: Mapped[Category] = mapped_column(SAEnum(Category, name="category_type"))

    title: Mapped[str] = mapped_column(String(255))
    base_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    store_discount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    # menu_item 가격 비교에서 자동 생성된 오퍼면 그 메뉴를 가리킨다 (재계산/삭제 시 추적용).
    menu_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_item.id", ondelete="CASCADE"), nullable=True
    )

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ttl_sec: Mapped[int | None] = mapped_column(Integer)

    place = relationship("Place", back_populates="offers")
    payment_benefits = relationship(
        "OfferPaymentBenefit", back_populates="offer", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_offer_place_id", "place_id"),
        Index("ix_offer_expires_at", "expires_at"),
        Index("ix_offer_layer", "layer"),
        Index("ix_offer_category", "category"),
    )


class OfferPaymentBenefit(Base):
    __tablename__ = "offer_payment_benefit"

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offer.id", ondelete="CASCADE"))
    method_type: Mapped[PaymentMethodType] = mapped_column(
        SAEnum(PaymentMethodType, name="payment_method_type")
    )
    benefit_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    benefit_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))

    offer = relationship("Offer", back_populates="payment_benefits")
