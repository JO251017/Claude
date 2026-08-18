from geoalchemy2 import Geometry
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.spatial import WGS84_SRID
from app.domain.base import Base, TimestampMixin
from app.domain.enums import Category, ReportStatus


class UserReport(Base, TimestampMixin):
    __tablename__ = "user_report"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    ocr_json: Mapped[dict | None] = mapped_column(JSONB)
    ai_category: Mapped[Category | None] = mapped_column(SAEnum(Category, name="category_type"))
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus, name="report_status"), default=ReportStatus.PENDING
    )
    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=WGS84_SRID, spatial_index=False)
    )
    # 제보 → 실제 지도 반영(2026-08-18, "즉시 게시 + 기존 신뢰도 시스템에 편입") —
    # 예전엔 PENDING 상태로 저장만 되고 Place/Offer로 바뀌는 코드가 어디에도
    # 없어서 제보가 지도에 영원히 안 뜨는 완전히 끊긴 기능이었다. 이제
    # ReportPipeline.ingest()가 위치(geom)를 확보하면 즉시 Place+Offer를 만들고
    # 여기 연결해둔다 — 위치가 없으면(geom is None) 연결 없이 PENDING으로 남는다.
    # ON DELETE SET NULL: place/offer가 나중에 지워져도 제보 기록 자체(사진 증거,
    # 감사 로그)는 남는다.
    place_id: Mapped[int | None] = mapped_column(ForeignKey("place.id", ondelete="SET NULL"))
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offer.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("ix_user_report_geom_gist", "geom", postgresql_using="gist"),
        Index("ix_user_report_place_id", "place_id"),
    )
