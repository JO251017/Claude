from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Index, String
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

    offers = relationship("Offer", back_populates="place", cascade="all, delete-orphan")
    menu_items = relationship("MenuItem", back_populates="place", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_place_geom_gist", "geom", postgresql_using="gist"),
        Index("ix_place_h3_r9", "h3_r9"),
        Index("ix_place_owner_user_id", "owner_user_id"),
    )
