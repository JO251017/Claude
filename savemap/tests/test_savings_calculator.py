from app.domain.enums import Category, Layer, PaymentMethodType
from app.engine.models import OfferCandidate, PaymentBenefit
from app.engine.savings_calculator import calculate_savings


def _candidate(**kw) -> OfferCandidate:
    base = dict(
        offer_id=1,
        place_id=1,
        place_name="A식당",
        category=Category.DISCOUNT,
        layer=Layer.REGULAR,
        distance_m=100.0,
        base_price=10000.0,
    )
    base.update(kw)
    return OfferCandidate(**base)


def test_store_discount_only():
    b = calculate_savings(_candidate(store_discount=3000.0))
    assert b.final_price == 7000.0
    assert b.savings_rate == 30.0


def test_stacked_card_discount():
    c = _candidate(
        store_discount=3000.0,
        payment_benefits=[PaymentBenefit(PaymentMethodType.CARD, rate=0.10)],
    )
    b = calculate_savings(c)
    assert b.payment_discount == 700.0
    assert b.final_price == 6300.0
    assert b.savings_rate == 37.0


def test_discount_never_exceeds_base():
    b = calculate_savings(_candidate(base_price=5000.0, store_discount=9999.0))
    assert b.final_price == 0.0
    assert b.total_savings == 5000.0


def test_zero_base_price_is_safe():
    b = calculate_savings(_candidate(base_price=0.0))
    assert b.savings_rate == 0.0
    assert b.final_price == 0.0
