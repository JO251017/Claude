from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.spatial import WGS84_SRID
from app.domain.base import Base, TimestampMixin


class Place(Base, TimestampMixin):
    __tablename__ = "place"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500))
    kakao_place_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    # 카카오 로컬 API가 준 실제 업종 문자열 (예: "음식점 > 한식 > 국밥").
    # SaveMap이 메뉴를 직접 보여주지 않는 대신, 무슨 업종인지는 알려줘야 하기 때문에 저장한다.
    category_name: Mapped[str | None] = mapped_column(String(255))
    owner_user_id: Mapped[str | None] = mapped_column(String(64))
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=WGS84_SRID, spatial_index=False)
    )
    h3_r9: Mapped[int | None] = mapped_column(BigInteger)
    # 전국지역화폐가맹점표준데이터(공공데이터포털)와 매칭돼 "실제 지역화폐 가맹점"으로
    # 확인된 매장인지. PaymentMethodDerived(app/domain/payment_method.py)는 사용자가
    # 스스로 "이 결제수단 있음"이라고 신고하는 값이라 매장이 진짜 가맹점인지와는
    # 무관하다 — 이 필드는 매장 자체의 사실이라 사용자별이 아니라 Place에 직접 둔다.
    # 금액/할인율은 이 데이터에 없어서 만들어내지 않는다(혜택 계산에는 안 씀,
    # 검색 결과에 배지로만 노출).
    accepts_local_currency: Mapped[bool] = mapped_column(Boolean, default=False)
    local_currency_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    offers = relationship("Offer", back_populates="place", cascade="all, delete-orphan")
    menu_items = relationship("MenuItem", back_populates="place", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_place_geom_gist", "geom", postgresql_using="gist"),
        Index("ix_place_h3_r9", "h3_r9"),
        Index("ix_place_owner_user_id", "owner_user_id"),
    )
