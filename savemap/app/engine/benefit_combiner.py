from app.domain.enums import PaymentMethodType
from app.engine.models import OfferCandidate, PaymentBenefit


def applicable_benefits(
    candidate: OfferCandidate, owned_methods: set[PaymentMethodType]
) -> list[PaymentBenefit]:
    return [b for b in candidate.payment_benefits if b.method_type in owned_methods]


def combine(candidates: list[OfferCandidate], owned_methods: set[PaymentMethodType]) -> None:
    for candidate in candidates:
        candidate.payment_benefits = applicable_benefits(candidate, owned_methods)
