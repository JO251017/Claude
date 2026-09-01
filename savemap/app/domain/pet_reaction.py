from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin


class PetStageMessage(Base, TimestampMixin):
    """펫 AI 반응(2026-09-01, AI MVP §D) — 레벨업 축하 대사 캐시.

    사용자별이 아니라 **성장 단계(stage_index)당 전역으로 하나만** 캐시한다 —
    대사 내용이 그 단계 이름 하나만 근거로 하는 순수 축하 문구라 사용자마다
    달라질 이유가 없고, 전역 캐시면 앱 전체 수명 동안 이 단계에 대한 Gemini
    호출이 정확히 한 번만 일어난다(§5 "AI 호출 비용 최소화"). 다른 이벤트
    (발견/방문/추천/제보/인증/스트릭)는 이 테이블을 안 쓴다 — 그쪽은 프론트
    템플릿 로테이션만으로 충분하고 굳이 AI를 부를 이유가 없다(레벨업만 "필요한
    상황"으로 판단, §5 원칙)."""

    __tablename__ = "pet_stage_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_index: Mapped[int] = mapped_column(Integer, unique=True)
    message: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16))  # "ai" | "template"

    __table_args__ = (Index("ix_pet_stage_message_stage_index", "stage_index"),)
