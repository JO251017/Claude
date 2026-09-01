import asyncio

from app.gamification.service import (
    EXPLORER_TITLE_THRESHOLDS,
    GROWTH_WEIGHT,
    RECOMMEND_TITLE_THRESHOLDS,
    VISIT_TITLE_THRESHOLDS,
    compute_explorer_title,
    compute_growth_score,
    compute_recommend_title,
    compute_visit_title,
    get_discovered_place_count,
    get_growth_score,
    get_recommended_place_count,
    get_savings_summary,
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
    assert s.title == "쓸모 전설"
    assert s.next_threshold is None
    assert s.remaining_to_next is None


def test_beyond_max_tier_stays_at_top_title():
    # 방문 매장 수는 상한 없이 계속 늘 수 있지만, 최고 칭호 문구는 고정된다 —
    # 절약금액 레벨(compute_savings_level)과 달리 초과 확장 로직이 없다.
    s = compute_explorer_title(250)
    assert s.title == "쓸모 전설"
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


# --- 방문 횟수 칭호 (2-2) --- compute_explorer_title과 같은 사다리 로직
# (_walk_count_thresholds)을 공유하므로 경계값 검증은 얇게만 둔다.
def test_visit_title_starts_at_base():
    s = compute_visit_title(0)
    assert s.title == "방문 새내기"
    assert s.next_threshold == 5


def test_visit_title_mid_and_max_tier():
    assert compute_visit_title(10).title == "동네 단골"
    assert compute_visit_title(29).title == "동네 단골"
    assert compute_visit_title(100).title == "쓸모 터줏대감"
    assert compute_visit_title(100).next_threshold is None


def test_visit_title_negative_clamped_to_zero():
    s = compute_visit_title(-5)
    assert s.visit_count == 0
    assert s.title == "방문 새내기"


def test_visit_thresholds_sorted_ascending():
    amounts = [amount for amount, _ in VISIT_TITLE_THRESHOLDS]
    assert amounts == sorted(amounts)


# --- 추천 횟수 칭호 (2-2) ---
def test_recommend_title_starts_at_base():
    s = compute_recommend_title(0)
    assert s.title == "추천 새내기"
    assert s.next_threshold == 5


def test_recommend_title_mid_and_max_tier():
    assert compute_recommend_title(30).title == "추천왕"
    assert compute_recommend_title(100).title == "추천의 신"
    assert compute_recommend_title(100).next_threshold is None


def test_recommend_thresholds_sorted_ascending():
    amounts = [amount for amount, _ in RECOMMEND_TITLE_THRESHOLDS]
    assert amounts == sorted(amounts)


def test_get_recommended_place_count_returns_session_scalar():
    session = _FakeSession(count=12)
    result = asyncio.run(get_recommended_place_count(session, "user-1"))
    assert result == 12


# --- get_savings_summary 기간별 합계 (2-1) --- 두 번의 execute 호출(총합/건수 →
# 기간별 조건부 합계)을 순서대로 다른 값으로 응답하는 FakeSession으로 today/
# weekly/monthly/yearly가 응답 필드에 그대로 실리는지만 확인한다(SQL 조건 자체의
# 날짜 경계 정확성은 SQLite/Postgres 없는 이 샌드박스에서 검증 불가 — 값 전달
# 경로만 검증).
class _FakeOneResult:
    def __init__(self, value):
        self._value = value

    def one(self):
        return self._value


class _FakeSummarySession:
    def __init__(self, rows):
        self._rows = list(rows)

    async def execute(self, *a, **kw):
        return _FakeOneResult(self._rows.pop(0))


def test_get_savings_summary_carries_period_totals_through():
    session = _FakeSummarySession(
        rows=[
            (100_000, 6),  # 총합, 건수
            (1_000, 5_000, 20_000, 80_000),  # today, weekly, monthly, yearly
        ]
    )
    summary = asyncio.run(get_savings_summary(session, "user-1"))
    assert summary.total_saved == 100_000.0
    assert summary.certification_count == 6
    assert summary.today_saved == 1_000.0
    assert summary.weekly_saved == 5_000.0
    assert summary.monthly_saved == 20_000.0
    assert summary.yearly_saved == 80_000.0


# --- 펫 성장치(2026-09-01 재조정, 새 펫 이미지 지시서 값으로 교체:
# 발견 5/추천 15/방문 30/구매 인증(직접입력) 50/영수증 인증 100) ---


def test_compute_growth_score_applies_confirmed_weights():
    assert GROWTH_WEIGHT == {
        "discover": 5,
        "recommend": 15,
        "visit": 30,
        "certify_direct": 50,
        "certify_receipt": 100,
    }
    score = compute_growth_score(
        discovered_place_count=3,
        visited_place_count=2,
        recommend_count=1,
        direct_certified_count=1,
        receipt_certified_count=1,
    )
    assert score == 3 * 5 + 2 * 30 + 1 * 15 + 1 * 50 + 1 * 100  # 15+60+15+50+100 = 240


def test_compute_growth_score_zero_activity_is_zero():
    assert compute_growth_score(0, 0, 0, 0, 0) == 0


def test_compute_growth_score_direct_and_receipt_certification_both_contribute():
    # 이번 지시서부터 직접입력(자기신고)도 0이 아닌 값을 받는다 — 영수증
    # 인증(사진 검증)의 절반 무게.
    assert compute_growth_score(0, 0, 0, direct_certified_count=3, receipt_certified_count=0) == 3 * 50
    assert compute_growth_score(0, 0, 0, direct_certified_count=0, receipt_certified_count=3) == 3 * 100


class _FakeGrowthSession:
    """get_visited_place_count → get_direct_certified_count → get_receipt_certified_count
    순서로 execute를 세 번 부른다(전부 scalar_one())."""

    def __init__(self, visited: int, direct_certified: int, receipt_certified: int):
        self._queue = [
            _FakeScalarResult(visited),
            _FakeScalarResult(direct_certified),
            _FakeScalarResult(receipt_certified),
        ]

    async def execute(self, *a, **kw):
        return self._queue.pop(0)


def test_get_growth_score_combines_query_results_with_passed_in_counts():
    session = _FakeGrowthSession(visited=4, direct_certified=1, receipt_certified=2)
    score = asyncio.run(
        get_growth_score(session, "user-1", discovered_place_count=10, recommend_count=3)
    )
    assert score == compute_growth_score(10, 4, 3, 1, 2)
