from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin


class MenuSynonymCandidate(Base, TimestampMixin):
    """AI 동의어 후보(2026-09-04) — "표기만 다른 같은 메뉴"로 보이는 (variant,
    canonical) 후보를 저장만 하고, 실제 정규화 규칙(app/engine/menu_name.py의
    _SYNONYMS)에는 자동으로 반영하지 않는다.

    왜 자동 반영을 안 하는가: 잘못 합치면 값이 다른 메뉴끼리 비교하게 돼서
    없는 절약률을 만들어낸다(예: "삼겹살"과 "대패삼겹살"을 AI가 헷갈릴 수
    있음). 그래서 이 테이블은 사람이 검토하기 전 "후보 목록"일 뿐이고, 실제
    코드(_SYNONYMS)에 넣는 건 항상 사람이 확인한 뒤 별도 커밋으로 한다
    (2026-09-03에 직접 검토해서 넣은 23쌍과 같은 절차).

    variant/canonical 둘 다 이미 normalize_menu_name의 앞단 정규화(괄호/구분자/
    크기접미사 제거)까지 거친 형태를 저장한다 — discover_menu_synonym_candidates가
    normalized_name(=이미 그 단계까지 거친 값)을 그대로 보내기 때문."""

    __tablename__ = "menu_synonym_candidate"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant: Mapped[str] = mapped_column(String(64))
    canonical: Mapped[str] = mapped_column(String(64))
    # AI가 왜 같은 메뉴로 봤는지 한 줄 — 검토할 때 이유가 있어야 판단이 빠르다.
    reason: Mapped[str | None] = mapped_column(String(200))
    # 후보 생성 시점의 매장 수(참고용) — 정규화가 실제로 얼마나 많은 실측
    # 비교를 살릴지 가늠하는 데 쓴다. 나중에 값이 바뀌어도 갱신하지 않는다.
    variant_places: Mapped[int | None] = mapped_column(Integer)
    canonical_places: Mapped[int | None] = mapped_column(Integer)
    # "pending"(검토 전) | "approved"(_SYNONYMS에 반영함) | "rejected"(다른 메뉴로 판단)
    status: Mapped[str] = mapped_column(String(16), default="pending")

    __table_args__ = (
        UniqueConstraint("variant", "canonical", name="uq_menu_synonym_candidate_pair"),
        Index("ix_menu_synonym_candidate_status", "status"),
    )
