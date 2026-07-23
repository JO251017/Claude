from dataclasses import dataclass

from app.core.config import settings
from app.engine.models import OfferCandidate
from app.engine.savings_calculator import SavingsBreakdown, calculate_savings


@dataclass
class RankedOffer:
    candidate: OfferCandidate
    breakdown: SavingsBreakdown
    score: float


def _score(breakdown: SavingsBreakdown, trust: float) -> float:
    savings_norm = min(breakdown.savings_rate / 100.0, 1.0)
    trust_norm = min(max(trust, 0.0), 1.0)
    return (
        savings_norm * settings.rank_savings_weight + trust_norm * settings.rank_trust_weight
    )


def rank_candidates(candidates: list[OfferCandidate]) -> list[RankedOffer]:
    ranked = []
    for candidate in candidates:
        breakdown = calculate_savings(candidate)
        ranked.append(RankedOffer(candidate, breakdown, _score(breakdown, candidate.trust_score)))
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked
