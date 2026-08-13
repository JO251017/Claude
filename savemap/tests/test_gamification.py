import asyncio

from app.gamification.service import (
    EXPLORER_TITLE_THRESHOLDS,
    compute_explorer_title,
    get_discovered_place_count,
)


def test_zero_visits_starts_at_base_title():
    s = compute_explorer_title(0)
    assert s.title == "동네 초보"
    assert s.next_threshold == 5
    assert s.remaining_to_next == 5


def test_negative_count_clamped_to_zero():
    s = compute_explorer_title(-3)
    assert s.discovered_place_count == 0
    assert s.title == "동네 초보"


def test_just_below_threshold_keeps_previous_title():
    s = compute_explorer_title(4)
    assert s.title == "동네 초보"
    assert s.remaining_to_next == 1


def test_exact_threshold_reaches_new_title():
    s = compute_explorer_title(5)
    assert s.title == "동네 탐방러"
    assert s.next_threshold == 10
    assert s.remaining_to_next == 5


def test_between_thresholds_keeps_lower_title():
    s = compute_explorer_title(9)
    assert s.title == "동네 탐방러"
    assert s.remaining_to_next == 1


def test_mid_thresholds():
    assert compute_explorer_title(10).title == "골목 탐험가"
    assert compute_explorer_title(29).title == "골목 탐험가"
    assert compute_explorer_title(30).title == "발품왕"
    assert compute_explorer_title(49).title == "발품왕"
    assert compute_explorer_title(50).title == "동네 마스터"
    assert compute_explorer_title(99).title == "동네 마스터"


def test_max_tier_has_no_next_threshold():
    s = compute_explorer_title(100)
    assert s.title == "SaveMap 전설"
    assert s.next_threshold is None
    assert s.remaining_to_next is None


def test_beyond_max_tier_stays_at_top_title():
    # 방문 매장 수는 상한 없이 계속 늘 수 있지만, 최고 칭호 문구는 고정된다 —
    # 절약금액 레벨(compute_savings_level)과 달리 초과 확장 로직이 없다.
    s = compute_explorer_title(250)
    assert s.title == "SaveMap 전설"
    assert s.discovered_place_count == 250
    assert s.next_threshold is None


def test_thresholds_are_sorted_ascending():
    amounts = [amount for amount, _ in EXPLORER_TITLE_THRESHOLDS]
    assert amounts == sorted(amounts)


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _FakeSession:
    def __init__(self, count: int):
        self._count = count

    async def execute(self, *a, **kw):
        return _FakeScalarResult(self._count)


def test_get_discovered_place_count_returns_session_scalar():
    session = _FakeSession(count=7)
    result = asyncio.run(get_discovered_place_count(session, "user-1"))
    assert result == 7
