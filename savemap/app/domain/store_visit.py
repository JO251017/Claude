from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric
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


class PlaceVisit(Base, TimestampMixin):
    """방문 GPS 인증 공식 기준(2026-09-01, 사용자 확정)을 전부 통과한 확정 방문 —
    거리 50m 이내 + GPS 정확도 30m 이내 + 서로 다른 시점 2회 연속 측정 + 사용자가
    [방문 기록] 버튼 클릭 + 서버 재검증까지 마친 것만 이 테이블에 남는다.

    StoreStatusUpdate(발견하기=영업상태 제보, 100m/1회 측정)와는 다른 행동이다 —
    이건 "내가 오늘 여기 갔다"는 개인 활동 기록이고, 판정 기준도 훨씬 엄격하다.
    두 테이블을 합치지 않는 이유: 발견하기는 매장 정보 갱신에 기여하는 제보라
    같은 사람이 반복해도 되는데, 방문은 하루 1회로 막아야 하는 서로 다른 제약을
    갖는다."""

    __tablename__ = "place_visit"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    lat: Mapped[float] = mapped_column(Numeric(9, 6))
    lng: Mapped[float] = mapped_column(Numeric(9, 6))
    gps_accuracy: Mapped[float] = mapped_column(Numeric(6, 2))
    distance_at_visit: Mapped[float] = mapped_column(Numeric(8, 2))
    # KST 기준 날짜 — 하루 1회 제한을 DB 유니크 제약으로 강제하는 축(app/
    # gamification/streak.py의 _to_kst_date와 같은 기준으로 애플리케이션에서 채운다).
    visit_date: Mapped[date] = mapped_column(Date)
    # 클라이언트가 측정한 시각 — 참고용 기록일 뿐, 판정에는 서버가 받은 시각
    # (created_at)만 쓴다(클라이언트 값을 최종 판정에 신뢰하지 않는다는 원칙).
    client_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "user_id", "place_id", "visit_date", name="uq_place_visit_user_place_date"
        ),
        Index("ix_place_visit_user_id", "user_id"),
    )
