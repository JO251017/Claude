from app.domain.place import Place
from app.engine.price_discovery.candidate_selector import (
    ADDRESS_BONUS,
    CATEGORY_BONUS,
    FRANCHISE_BONUS,
    PHONE_BONUS,
    _candidate_stmt,
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


# --- 실사용 중 발견된 버그(2026-08-31): 주차장/체육시설처럼 MenuItem이 원래
# 있을 수 없는 매장이 "가격 없음" 조건만 보고 후보로 잘못 뽑혔었다. ---


def test_candidate_stmt_excludes_free_parking_and_local_benefit_offers():
    compiled = str(_candidate_stmt(region=None, pool_limit=100).compile(compile_kwargs={"literal_binds": True}))
    assert "offer" in compiled.lower()
    assert "FREE_PARKING" in compiled or "free_parking" in compiled.lower()
    assert "LOCAL_BENEFIT" in compiled or "local_benefit" in compiled.lower()


def test_candidate_stmt_still_filters_priced_and_active_job_places():
    compiled = str(_candidate_stmt(region=None, pool_limit=100).compile(compile_kwargs={"literal_binds": True}))
    assert "menu_item" in compiled.lower()
    assert "price_discovery_job" in compiled.lower()


def test_candidate_stmt_applies_region_filter_when_given():
    with_region = str(_candidate_stmt(region="평택시", pool_limit=100).compile(compile_kwargs={"literal_binds": True}))
    without_region = str(_candidate_stmt(region=None, pool_limit=100).compile(compile_kwargs={"literal_binds": True}))
    assert "평택시" in with_region
    assert "평택시" not in without_region
