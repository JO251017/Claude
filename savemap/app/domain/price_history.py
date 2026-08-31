from datetime import datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin
from app.domain.enums import SourceType


class PriceHistory(Base, TimestampMixin):
    """MenuItem.price가 바뀔 때마다 이전 값을 지우지 않고 남긴 이력 한 줄
    (vNext 지시서, 2026-08-31, "가격 이력 관리" — "김치찌개 8,000원 → 8,500원 →
    9,000원"처럼 지금까지의 값을 그대로 보존한다). 이전엔 app/engine/offer_sync.py의
    sync_menu_offer가 MenuItem/Offer 행을 직접 덮어써서 이력이 통째로 사라졌다.

    항상 sync_menu_offer를 거쳐서만 기록된다 — MenuItem.price를 바꾸는 모든 경로
    (community_menu, merchant_console, good_price/franchise_price/dine_out_price
    같은 공공데이터 적재, 그리고 향후 AI Price Discovery)가 이미 그 함수를 호출하고
    있어서, 새 저장 경로를 따로 만들지 않고 이 한 지점에서만 이력을 남긴다. 값이
    실제로 안 바뀐 재동기화는 새 행을 만들지 않는다(직전 is_current 행과 가격이
    같으면 건너뜀) — 안 그러면 오퍼 재동기화 배치가 돌 때마다 이력이 무한정 쌓인다.
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_item.id", ondelete="CASCADE"))
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    # MenuItem.source(누가/무엇이 이 가격을 알려줬는지)와 같은 축이라 별도 개념을
    # 새로 만들지 않고 그대로 재사용한다 — Offer.benchmark_source(region/gov/ai,
    # "무엇과 비교했는지")와는 다른 개념이니 혼동하지 않는다.
    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type"))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 근거 요약 한 줄(500자 제한) — 원본 이미지 전체나 웹 자료 원문은 저장하지
    # 않는다(개인정보/저작권 최소화, AI Price Discovery 지시서 28-15/28-31 선반영).
    evidence_text: Mapped[str | None] = mapped_column(String(500))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_price_history_menu_item_id", "menu_item_id"),
        # sync_menu_offer가 호출될 때마다 "이 메뉴의 현재가"를 찾아 가격이 바뀌었는지
        # 판단해야 한다 — 이 복합 인덱스가 없으면 이력이 쌓일수록 매번 그 메뉴의
        # 전체 이력을 훑게 된다.
        Index("ix_price_history_menu_item_current", "menu_item_id", "is_current"),
    )
