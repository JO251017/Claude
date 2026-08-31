import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin


class DiscoveryJobStatus(str, enum.Enum):
    """AI Price Discovery Engine 지시서 28-18의 상태값 그대로."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class PriceDiscoveryJob(Base, TimestampMixin):
    """가격 없는 매장 하나를 조사하는 작업 단위 큐. 실제 가격/출처는 이 테이블에
    안 담는다 — 승인되면 기존 파이프라인(app/engine/offer_sync.py:sync_menu_offer)을
    그대로 태워 MenuItem/Offer/PriceHistory에 반영한다(28-33, "이미 동일 목적
    테이블 있으면 확장" 원칙 — price_sources/price_evidence를 별도로 만들지 않고
    price_history를 재사용한다)."""

    __tablename__ = "price_discovery_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    status: Mapped[DiscoveryJobStatus] = mapped_column(
        SAEnum(DiscoveryJobStatus, name="discovery_job_status"),
        default=DiscoveryJobStatus.PENDING,
    )
    # candidate_selector가 매긴 조사 우선순위(가격 자체의 신뢰도가 아니다 — "이
    # 매장을 먼저 조사할 가치가 있는가"만 뜻함, 지시서 28-3).
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(32))
    # 사람이 훑어보기 위한 요약 한 줄(예: "가격 3건 발견 / 자동승인 2 / 검토대기 1")
    # — AI가 만든 원문이나 이미지는 절대 안 남긴다(28-31).
    result_summary: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index("ix_price_discovery_job_place_id", "place_id"),
        Index("ix_price_discovery_job_status_priority", "status", "priority"),
    )
