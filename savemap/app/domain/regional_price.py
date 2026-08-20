from sqlalchemy import Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin


class RegionalPriceStat(Base, TimestampMixin):
    """한국소비자원 참가격이 매달 조사하는 외식비 시도별 평균가격.

    매장 하나하나의 가격이 아니라 시도 단위 통계다. 그래서 개별 매장 실측 비교를
    대체하지 않고, **주변에 비교할 매장이 아직 없을 때** 쓰던 자리(그동안 Gemini가
    짐작한 `MenuItem.ai_typical_price`가 차지하던 자리)를 정부 공식 통계로 바꾸는
    용도다. 우선순위는 항상 실측 > 정부 통계 > AI 추정이다.
    """

    __tablename__ = "regional_price_stat"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 참가격 외식비 8개 품목 중 하나 (menu_name.canonical_dish가 돌려주는 값과 같다).
    dish: Mapped[str] = mapped_column(String(64))
    # 시도명. 표기가 출처마다 갈려서("충남" / "충청남도") 저장 전에 짧은 형태로 통일한다.
    region: Mapped[str] = mapped_column(String(32))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    # 조사 시점("2026-07"). 통계가 언제 것인지 사용자에게 밝히기 위해 저장한다 —
    # 출처를 감춘 채 숫자만 보여주지 않는다는 이 프로젝트의 원칙 그대로.
    survey_period: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        UniqueConstraint("dish", "region", name="uq_regional_price_dish_region"),
        Index("ix_regional_price_dish_region", "dish", "region"),
    )
