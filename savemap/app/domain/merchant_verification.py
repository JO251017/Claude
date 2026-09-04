from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin


class MerchantVerification(Base, TimestampMixin):
    """사업자로 인증된 사용자 (2-3, 2026-08-13) — 이 테이블에 user_id 행이 있어야만
    사업자 콘솔(매장/메뉴/혜택 등록)에 접근할 수 있다. 지금까지는 RequireUserDep
    (로그인 여부만 확인)만 걸려 있어 로그인만 하면 누구나 매장을 등록해 그 owner가
    될 수 있었다 — 이 테이블 + require_merchant_verified 의존성으로 실제 접근
    제어를 추가한다. 부여/해제는 관리자 전용 엔드포인트(app/api/v1/admin.py)에서만
    가능하다(자동 심사는 이번 최소 기능 범위에 없음). TimestampMixin의 created_at이
    곧 인증 부여 시각이다."""

    __tablename__ = "merchant_verification"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
