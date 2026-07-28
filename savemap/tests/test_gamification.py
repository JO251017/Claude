from app.gamification.service import compute_level


def test_zero_xp_is_level_1():
    s = compute_level(0)
    assert s.level == 1
    assert s.title == "짠지망생"


def test_level_up_boundary():
    s = compute_level(50)
    assert s.level == 2
    assert s.xp_into_level == 0


def test_title_changes_at_tier_boundary():
    s = compute_level(9 * 50)
    assert s.level == 10
    assert s.title == "절약 탐험가"


def test_high_xp_reaches_top_tier():
    s = compute_level(3000)
    assert s.level == 61
    assert s.title == "절약의 신"


def test_negative_xp_clamped_to_zero():
    s = compute_level(-100)
    assert s.total_xp == 0
    assert s.level == 1
