from dataclasses import dataclass

from app.engine.models import OfferCandidate


@dataclass
class SavingsBreakdown:
    base_price: float
    store_discount: float
    payment_discount: float
    final_price: float
    total_savings: float
    savings_rate: float


def calculate_savings(candidate: OfferCandidate) -> SavingsBreakdown:
    base = max(candidate.base_price or 0.0, 0.0)
    store = min(max(candidate.store_discount or 0.0, 0.0), base)
    after_store = base - store

    payment_discount = 0.0
    for benefit in candidate.payment_benefits:
        payment_discount += after_store * (benefit.rate or 0.0)
        payment_discount += benefit.amount or 0.0
    payment_discount = min(payment_discount, after_store)

    final_price = after_store - payment_discount
    total_savings = base - final_price
    savings_rate = (total_savings / base * 100.0) if base > 0 else 0.0

    return SavingsBreakdown(
        base_price=round(base, 2),
        store_discount=round(store, 2),
        payment_discount=round(payment_discount, 2),
        final_price=round(final_price, 2),
        total_savings=round(total_savings, 2),
        savings_rate=round(savings_rate, 2),
    )
