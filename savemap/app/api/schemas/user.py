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
