from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.base import Base, TimestampMixin
from app.domain.enums import Category, Layer, PaymentMethodType, SourceType


class Offer(Base, TimestampMixin):
    __tablename__ = "offer"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    source: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type"))
    layer: Mapped[Layer] = mapped_column(SAEnum(Layer, name="layer_type"))
    category: Mapped[Category] = mapped_column(SAEnum(Category, name="category_type"))

    title: Mapped[str] = mapped_column(String(255))
    base_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    store_discount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    # 절약액을 무엇과 비교해 계산했는지: "region"=주변 매장 실제 등록가와 비교(신뢰 높음),
    # "gov"=한국소비자원 참가격 시도 평균(정부 조사 통계), "ai"=Gemini가 추정한 통상가와
    # 비교(참고용), None=비교 대상 없이 등록가 그대로. 검색 응답(AI 절약 리포트)이 "실측
    # 데이터 반영"이라고 말할 자격이 있는지 정확히 판단하려면 계산 당시 기준을 저장해둬야
    # 한다 — 다만 이 필드는 검색 시점에 재계산되지 않는다. 나중에 지역 표본이 쌓이거나
    # 새 벤치마크 소스가 채워져도, 관리자가 재동기화 배치(admin.resync_offers_endpoint,
    # app/engine/offer_resync.py)를 돌려야만 그 시점 기준으로 갱신된다.
    benchmark_source: Mapped[str | None] = mapped_column(String(16))
    # 계산 당시 이웃 매장 표본 수(region 기준일 때만 의미 있음) — "이웃 2곳"과 "이웃
    # 30곳"을 신뢰도 등급에서 구분하기 위해 굳혀 저장한다. 재동기화 전 구 데이터는 None.
    benchmark_sample_count: Mapped[int | None] = mapped_column(Integer)
    # 마지막으로 이 오퍼의 벤치마크를 재계산한 시각. updated_at으로는 대체할 수 없다 —
    # 값이 안 바뀌면 SQLAlchemy가 UPDATE 자체를 안 내보내서 updated_at이 안 오르기
    # 때문에, "오래된 것만 재동기화" 같은 판단이 불가능해진다.
    benchmark_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # menu_item 가격 비교에서 자동 생성된 오퍼면 그 메뉴를 가리킨다 (재계산/삭제 시 추적용).
    menu_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_item.id", ondelete="CASCADE"), nullable=True
    )

    # AI 활용 확대 안건 D(2026-08-31, "매장 카드 AI 한 줄 소개") — 검색 응답의
    # one_line은 지금까지 savings_report.py가 매 요청마다 결정론적 템플릿 문자열
    # 몇 종류만 돌려썼다(그 설계 이유는 그대로 유효 — 매 요청마다 LLM을 부르면
    # 느리고 비싸고 문구가 들쭉날쭉해진다). 그 원칙은 안 건드리고, 대신 이 값을
    # 관리자 배치(app/engine/offer_blurb_backfill.py)가 미리 한 번만 생성해
    # 캐시해둔다 — 검색 시점엔 이 컬럼이 있으면 그대로 쓰고, 없으면 기존 템플릿
    # 문구로 폴백한다(app/engine/result_assembly.py). AI 출력은 반드시 실제 사실
    # (카테고리/비교 기준/표본 수)만 근거로 하고 새 숫자를 만들면 그 결과를 통째로
    # 버리는 검증(app/engine/ai_text_guard.py)을 통과한 것만 여기 저장된다.
    ai_one_line: Mapped[str | None] = mapped_column(String(200))
    ai_one_line_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ttl_sec: Mapped[int | None] = mapped_column(Integer)

    place = relationship("Place", back_populates="offers")
    payment_benefits = relationship(
        "OfferPaymentBenefit", back_populates="offer", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_offer_place_id", "place_id"),
        Index("ix_offer_expires_at", "expires_at"),
        Index("ix_offer_layer", "layer"),
        Index("ix_offer_category", "category"),
        # sync_menu_offer가 매 호출마다 menu_item_id로 기존 오퍼를 찾는다 — 재동기화
        # 배치가 수만 건을 돌 때 이 인덱스가 없으면 건당 풀스캔이 난다.
        Index("ix_offer_menu_item_id", "menu_item_id"),
    )


class OfferPaymentBenefit(Base):
    __tablename__ = "offer_payment_benefit"

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offer.id", ondelete="CASCADE"))
    method_type: Mapped[PaymentMethodType] = mapped_column(
        SAEnum(PaymentMethodType, name="payment_method_type")
    )
    benefit_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    benefit_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))

    offer = relationship("Offer", back_populates="payment_benefits")
