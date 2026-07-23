from geoalchemy2 import Geometry
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, String
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

    __table_args__ = (Index("ix_user_report_geom_gist", "geom", postgresql_using="gist"),)
