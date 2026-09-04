from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.domain.base import Base, TimestampMixin
from app.engine.menu_name import normalize_menu_name


class FranchiseBrand(Base, TimestampMixin):
    """프랜차이즈 브랜드와, 상호명에서 이 브랜드를 알아보기 위한 매칭 키워드.

    체인점은 본사가 공식 가격을 공개하고 전국이 대체로 같은 값이라, 브랜드 가격표를
    한 번 넣어두면 상호명 매칭만으로 수천 개 매장의 가격이 채워진다 — 인허가 데이터로
    들어온 매장 대부분이 이름만 있고 가격이 비어 있는 상태를 메우는 가장 값싼 방법이다.
    """

    __tablename__ = "franchise_brand"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    # 상호명 표기 흔들림을 흡수하기 위한 키워드 목록(파이프 구분: "스타벅스|starbucks").
    # 비워두면 브랜드명 자체를 키워드로 쓴다.
    match_keywords: Mapped[str | None] = mapped_column(String(512))
    # AI 매칭 키워드 제안(2026-09-04, 파이프 구분) — match_keywords와 별개
    # 컬럼이다: 여기에 뭐가 들어와도 실제 상호명 매칭(franchise_price.
    # matches_brand)에는 전혀 쓰이지 않는다. 브랜드 매칭이 잘못되면 엉뚱한
    # 매장에 엉뚱한 가격이 붙는다 — 동의어 후보(menu_synonym_candidate)보다도
    # 더 위험해서, 사람이 검토해 직접 match_keywords로 옮겨야만 실제로
    # 적용된다.
    suggested_match_keywords: Mapped[str | None] = mapped_column(String(512))
    # 본사 공식 가격 안내 페이지. 가격의 출처를 밝히기 위해 저장하고, 생성되는
    # MenuItem.source_url에 그대로 넣는다 — 어디서 온 값인지 추적할 수 없는 가격은
    # 이 프로젝트에서 쓰지 않는다.
    official_url: Mapped[str | None] = mapped_column(String(1024))

    prices = relationship(
        "FranchisePrice", back_populates="brand", cascade="all, delete-orphan"
    )


class FranchisePrice(Base, TimestampMixin):
    """브랜드 공식 메뉴 가격 한 줄."""

    __tablename__ = "franchise_price"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("franchise_brand.id", ondelete="CASCADE"))
    item_name: Mapped[str] = mapped_column(String(255))
    normalized_item_name: Mapped[str] = mapped_column(String(255), default="")
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    # 이 가격이 언제 기준인지("2026-08"). 체인 가격은 수시로 오르기 때문에, 언제
    # 것인지 밝히지 않은 가격은 사용자를 오도한다.
    effective_period: Mapped[str | None] = mapped_column(String(16))

    brand = relationship("FranchiseBrand", back_populates="prices")

    @validates("item_name")
    def _sync_normalized(self, _key: str, value: str) -> str:
        self.normalized_item_name = normalize_menu_name(value)[:255]
        return value

    __table_args__ = (
        UniqueConstraint("brand_id", "normalized_item_name", name="uq_franchise_price_item"),
        Index("ix_franchise_price_brand_id", "brand_id"),
    )
