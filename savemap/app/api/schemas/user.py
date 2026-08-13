from pydantic import BaseModel


class SavingsSummaryResponse(BaseModel):
    total_saved: float
    level: int
    title: str
    next_threshold: float | None
    remaining_to_next: float | None
    progress_pct: float
    certification_count: int
    monthly_saved: float = 0.0
    # 탐험가 칭호(2026-08-13) — 절약금액이 아니라 실제 방문 인증한 서로 다른 매장
    # 수 기반. 위 level/title(절약금액 기준)과는 독립된 축이라 explorer_ 접두어로
    # 스키마에서부터 확실히 구분한다("레벨 시스템 두 벌" 혼선을 반복하지 않기 위함).
    discovered_place_count: int
    explorer_title: str
    explorer_next_threshold: int | None
    explorer_remaining_to_next: int | None
