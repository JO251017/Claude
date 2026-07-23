from dataclasses import dataclass

from app.engine.ranker import RankedOffer


@dataclass
class RouteStop:
    ranked: RankedOffer
    arrive_at: str
    note: str


class RouteRecommender:
    def recommend(self, ranked: list[RankedOffer], budget: float, party_size: int) -> list[RouteStop]:
        raise NotImplementedError(
            "하이브리드 AI 동선 추천(Rule 후보 → Gemini 맥락 조합)은 후속 단계에서 구현"
        )
