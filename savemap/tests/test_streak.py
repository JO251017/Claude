import asyncio
from datetime import UTC, datetime, timedelta

from app.gamification.streak import get_streak_summary


class _FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeSession:
    """네 번의 session.execute 호출(인증/발견/추천/방문)에 순서대로 미리 정해둔
    created_at 리스트를 하나씩 돌려준다. visit_rows 생략 시 빈 리스트(기존
    테스트가 방문 축을 신경 쓰지 않아도 되게)."""

    def __init__(self, cert_rows, discover_rows, recommend_rows, visit_rows=()):
        self._queue = [cert_rows, discover_rows, recommend_rows, list(visit_rows)]

    async def execute(self, *a, **kw):
        return _FakeResult(self._queue.pop(0))


def _kst_days_ago(days: int) -> datetime:
    """오늘(KST)로부터 days일 전, KST 자정을 살짝 지난 시각의 UTC datetime을 만든다."""
    now_kst = datetime.now(UTC) + timedelta(hours=9)
    target_kst = now_kst.replace(hour=1, minute=0, second=0, microsecond=0) - timedelta(days=days)
    return target_kst - timedelta(hours=9)  # UTC로 되돌림


def test_no_activity_ever_gives_zero_streak():
    session = _FakeSession([], [], [])
    result = asyncio.run(get_streak_summary(session, "user-1"))
    assert result.current_streak == 0
    assert result.did_activity_today is False
    assert result.at_risk is False


def test_activity_today_only_counts_as_streak_one():
    session = _FakeSession([_kst_days_ago(0)], [], [])
    result = asyncio.run(get_streak_summary(session, "user-1"))
    assert result.current_streak == 1
    assert result.did_activity_today is True
    assert result.at_risk is False


def test_consecutive_days_across_all_three_sources_combine_into_one_streak():
    # 오늘=인증, 어제=발견, 그제=추천 — 서로 다른 활동 종류라도 날짜만 이어지면 스트릭.
    session = _FakeSession([_kst_days_ago(0)], [_kst_days_ago(1)], [_kst_days_ago(2)])
    result = asyncio.run(get_streak_summary(session, "user-1"))
    assert result.current_streak == 3
    assert result.did_activity_today is True


def test_gap_in_the_middle_breaks_streak_at_the_gap():
    # 오늘, 어제는 있는데 그제가 비어 있으면 스트릭은 2에서 멈춘다(그 이전 날짜는 무시).
    session = _FakeSession([_kst_days_ago(0), _kst_days_ago(1), _kst_days_ago(5)], [], [])
    result = asyncio.run(get_streak_summary(session, "user-1"))
    assert result.current_streak == 2


def test_no_activity_today_but_yesterday_streak_is_at_risk():
    session = _FakeSession([_kst_days_ago(1), _kst_days_ago(2)], [], [])
    result = asyncio.run(get_streak_summary(session, "user-1"))
    assert result.current_streak == 2
    assert result.did_activity_today is False
    assert result.at_risk is True


def test_streak_already_broken_two_days_ago_is_not_at_risk():
    # 어제도 안 했으면 이미 끊긴 상태 — "오늘 안에 하면 살아난다"는 긴급함(at_risk)이 아니다.
    session = _FakeSession([_kst_days_ago(3)], [], [])
    result = asyncio.run(get_streak_summary(session, "user-1"))
    assert result.current_streak == 0
    assert result.at_risk is False


def test_duplicate_activities_same_day_count_once():
    session = _FakeSession(
        [_kst_days_ago(0), _kst_days_ago(0), _kst_days_ago(0)], [], []
    )
    result = asyncio.run(get_streak_summary(session, "user-1"))
    assert result.current_streak == 1


def test_place_visit_alone_counts_as_activity():
    # 방문 GPS 인증(2026-09-01 신설)도 발견/인증/추천과 같은 축으로 스트릭에
    # 들어간다 — 다른 세 소스가 전부 비어 있어도 방문 하나만으로 스트릭이 잡힌다.
    session = _FakeSession([], [], [], visit_rows=[_kst_days_ago(0)])
    result = asyncio.run(get_streak_summary(session, "user-1"))
    assert result.current_streak == 1
    assert result.did_activity_today is True
