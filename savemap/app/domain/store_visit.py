from datetime import datetime

from sqlalchemy import DateTime, Numeric
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin
from app.domain.enums import BusinessStatus


class StoreStatusUpdate(Base, TimestampMixin):
    """사용자가 매장 반경 50m 이내에서 제출한 영업 상태. 가격 검증이나 실제 소비 인증이
    아니라 "최근에 실제 방문해서 영업 상태를 확인했다"는 사실만 의미한다 (기획서 §9)."""

    __tablename__ = "store_status_update"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    status: Mapped[BusinessStatus] = mapped_column(SAEnum(BusinessStatus, name="business_status"))
    lat: Mapped[float] = mapped_column(Numeric(9, 6))
    lng: Mapped[float] = mapped_column(Numeric(9, 6))
    distance_m: Mapped[float] = mapped_column(Numeric(8, 2))

    __table_args__ = (Index("ix_store_status_update_place_id", "place_id"),)


class StoreInterest(Base):
    """매장에 관심을 보인 고유 사용자(user_id, place_id 유일) — 실제 소비 인증과는
    별개의 지표다 (기획서 §10, §15). 동일 사용자가 반복 방문해도 중복 집계하지 않는다."""

    __tablename__ = "store_interest"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    first_interested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_interested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "place_id", name="uq_store_interest_user_place"),
        Index("ix_store_interest_place_id", "place_id"),
    )


class PlaceRecommendation(Base, TimestampMixin):
    """매장 추천(👍). 사용자당 매장 하나에 한 번만 집계된다 — AI 절약 리포트의
    "판단 근거"(사용자 추천 N건)에 실제 집계로만 반영하기 위함."""

    __tablename__ = "place_recommendation"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))

    __table_args__ = (
        UniqueConstraint("user_id", "place_id", name="uq_place_recommendation_user_place"),
        Index("ix_place_recommendation_place_id", "place_id"),
    )
