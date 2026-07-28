from pydantic import BaseModel


class XpSummaryResponse(BaseModel):
    total_xp: int
    level: int
    title: str
    xp_into_level: int
    xp_per_level: int
