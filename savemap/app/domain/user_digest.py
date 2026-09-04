from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin


class UserDigest(Base, TimestampMixin):
    """AI 활용 확대 안건 C(2026-08-31) — 개인화 절약 다이제스트 캐시.

    MY탭에 "이번 주 OO에서 제일 아꼈어요" 식 요약을 보여주되, 매 요청마다 AI를
    부르면(savings_report.py가 검색 응답 one_line을 절대 실시간 AI로 안 만드는
    것과 같은 이유로) 느리고 비싸다 — 한 사용자당 주(week_start) 1번만 생성해
    이 테이블에 캐시한다. 생성 시점은 TimestampMixin의 created_at으로 충분해
    별도 generated_at 컬럼을 안 둔다(이 행은 생성 후 수정되지 않는다).

    Render 무료 플랜엔 크론이 없어서(offer_blurb_backfill 같은 관리자 배치가
    아니라) MY탭 진입 시 그 자리에서 온디맨드로 생성한다 — GET /users/me/digest
    참고."""

    __tablename__ = "user_digest"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    # UTC 기준 그 주의 월요일 00:00 — app/gamification/service.get_savings_summary가
    # weekly_saved를 계산할 때 쓰는 week_start와 정확히 같은 기준이어야 다이제스트가
    # 인용하는 "이번 주 절약액"과 MY탭에 뜨는 숫자가 어긋나지 않는다.
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary_text: Mapped[str] = mapped_column(String(300))
    # "ai"|"template" — one_line_source(안건 D)와 같은 투명성 원칙: AI 문장인지
    # 결정론적 폴백인지 감추지 않는다.
    source: Mapped[str] = mapped_column(String(16))

    __table_args__ = (
        # 같은 사용자가 같은 주에 두 번 생성 요청을 동시에 보내는 레이스를 DB
        # 레벨에서 막는다 — price_discovery_job의 부분 유니크 인덱스와 같은 원칙
        # ("애플리케이션에서만 막지 않는다").
        Index("ux_user_digest_user_week", "user_id", "week_start", unique=True),
    )
