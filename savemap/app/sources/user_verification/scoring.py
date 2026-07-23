from app.domain.enums import Verdict


def recompute_trust(verdicts: list[tuple[Verdict, float]]) -> float:
    if not verdicts:
        return 0.5
    total_weight = sum(w for _, w in verdicts)
    if total_weight == 0:
        return 0.5
    available_weight = sum(w for v, w in verdicts if v == Verdict.AVAILABLE)
    return round(available_weight / total_weight, 4)
