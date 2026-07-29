from app.gamification.service import compute_savings_level


def test_zero_savings_is_level_1():
    s = compute_savings_level(0)
    assert s.level == 1
    assert s.title == "절약 초보"
    assert s.next_threshold == 10_000
    assert s.remaining_to_next == 10_000
    assert s.progress_pct == 0.0


def test_partial_progress_toward_next_level():
    s = compute_savings_level(4_500)
    assert s.level == 1
    assert s.progress_pct == 45.0
    assert s.remaining_to_next == 5_500


def test_exact_threshold_reaches_next_level():
    s = compute_savings_level(10_000)
    assert s.level == 2
    assert s.title == "짠지망생"
    assert s.progress_pct == 0.0


def test_top_defined_tier():
    s = compute_savings_level(1_000_000)
    assert s.level == 7
    assert s.title == "절약왕"
    assert s.next_threshold == 1_500_000


def test_beyond_top_tier_keeps_leveling_up():
    s = compute_savings_level(2_600_000)
    assert s.level == 10  # 1,000,000 + 3 * 500,000 = 2,500,000 <= 2,600,000
    assert s.title == "절약왕"


def test_negative_savings_clamped_to_zero():
    s = compute_savings_level(-500)
    assert s.total_saved == 0.0
    assert s.level == 1


def test_certification_count_is_passed_through():
    s = compute_savings_level(0, certification_count=3)
    assert s.certification_count == 3
