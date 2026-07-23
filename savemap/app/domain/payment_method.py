from sqlalchemy import Boolean, Enum as SAEnum
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin
from app.domain.enums import PaymentMethodType


class PaymentMethodDerived(Base, TimestampMixin):
    __tablename__ = "payment_method_derived"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    method_type: Mapped[PaymentMethodType] = mapped_column(
        SAEnum(PaymentMethodType, name="payment_method_type")
    )
    owned: Mapped[bool] = mapped_column(Boolean, default=True)
    grade: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (Index("ix_payment_method_user_id", "user_id"),)
