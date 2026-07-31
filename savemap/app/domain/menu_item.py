from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.base import Base, TimestampMixin
from app.domain.enums import SourceType


class MenuItem(Base, TimestampMixin):
    """매장의 개별 메뉴 가격. 절약률을 "이 매장은 싸다"처럼 뭉뚱그리지 않고
    메뉴 단위로(아메리카노 3,500원 vs 지역평균 4,800원) 비교하기 위한 기준 데이터."""

    __tablename__ = "menu_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    source: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type"))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 주변에 같은 메뉴를 등록한 매장이 아직 2곳 미만이라 실제 지역 비교가 안 될 때,
    # "이 가격이 싼 편인지" 참고용으로만 쓸 Gemini 추정 시세. 절약률/XP 계산에는 절대
    # 쓰지 않는다(지어내지 않기 원칙) — 등록 시 1회 추정해 캐싱, 실제 비교 데이터가
    # 쌓이면 그쪽이 항상 우선한다.
    ai_typical_price: Mapped[float | None] = mapped_column(Numeric(12, 2))

    place = relationship("Place", back_populates="menu_items")

    __table_args__ = (
        Index("ix_menu_item_place_id", "place_id"),
        Index("ix_menu_item_name", "name"),
    )
