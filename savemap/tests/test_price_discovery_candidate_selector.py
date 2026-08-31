from app.domain.place import Place
from app.engine.price_discovery.candidate_selector import (
    ADDRESS_BONUS,
    CATEGORY_BONUS,
    FRANCHISE_BONUS,
    PHONE_BONUS,
    _score,
)


def _place(**kw) -> Place:
    base = dict(id=1, name="가게", address=None, phone=None, category_name=None)
    base.update(kw)
    return Place(**base)


def test_score_is_zero_for_bare_place():
    assert _score(_place(), is_franchise=False) == 0


def test_franchise_bonus_applied():
    assert _score(_place(), is_franchise=True) == FRANCHISE_BONUS


def test_all_bonuses_stack():
    place = _place(address="충남 아산시", phone="041-123-4567", category_name="일반음식점 > 한식")
    assert _score(place, is_franchise=True) == (
        FRANCHISE_BONUS + PHONE_BONUS + ADDRESS_BONUS + CATEGORY_BONUS
    )


def test_more_complete_place_scores_higher():
    thin = _place()
    rich = _place(address="충남 아산시", phone="041-123-4567", category_name="일반음식점")
    assert _score(rich, is_franchise=False) > _score(thin, is_franchise=False)
