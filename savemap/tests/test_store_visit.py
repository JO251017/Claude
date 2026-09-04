import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    InvalidVisitReadingsError,
    LowGpsAccuracyVisitError,
    PlacePublicNotFoundError,
    StaleLocationReadingError,
    TooFarFromStoreError,
)
from app.domain.place import Place
from app.sources.store_visit.service import VisitReading, submit_visit

PLACE_LAT = 37.0
PLACE_LNG = 127.0


class _FakeCountResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _FakeSelectResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """execute/get/add/commit/rollback만 흉내 낸다 — tests/test_offer_sync.py,
    tests/test_community_menu_service.py와 같은 관례. execute 결과는 호출 순서대로
    큐에서 꺼낸다(submit_visit이 _existing_visit → (커밋) → _get_visit_count 순으로
    부르는 게 고정 순서라 이 방식으로 충분하다)."""

    def __init__(
        self, place: Place | None, existing_visit=None, visit_count=0, fail_first_commit=False
    ):
        self.place = place
        # submit_visit은 정확히 2번만 execute를 부른다: _existing_visit 조회,
        # 그리고 마지막 _get_visit_count. 새로 저장되는 경로면 그 사이에 커밋이
        # 끼어들 뿐 execute 횟수는 그대로다 — 최종 카운트를 그대로 둘째 자리에 둔다.
        final_count = visit_count if existing_visit is not None else visit_count + 1
        self._execute_queue = [
            _FakeSelectResult(existing_visit),
            _FakeCountResult(final_count),
        ]
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self._fail_first_commit = fail_first_commit

    async def get(self, model, pk):
        return self.place

    async def execute(self, *a, **kw):
        return self._execute_queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1
        if self._fail_first_commit and self.commits == 1:
            raise IntegrityError("dup", None, None)

    async def rollback(self):
        self.rollbacks += 1


def _readings(
    *,
    lat=PLACE_LAT,
    lng=PLACE_LNG,
    accuracy=10.0,
    gap_sec=3.0,
    base_ts=None,
):
    base_ts = base_ts or datetime.now(UTC) - timedelta(seconds=gap_sec)
    return [
        VisitReading(lat=lat, lng=lng, accuracy_m=accuracy, client_timestamp=base_ts),
        VisitReading(
            lat=lat, lng=lng, accuracy_m=accuracy,
            client_timestamp=base_ts + timedelta(seconds=gap_sec),
        ),
    ]


def _place():
    return Place(id=1, name="가게", address="주소", geom="fake-geom")


def _run(session, readings, place_id=1):
    with patch(
        "app.sources.store_visit.service.to_shape",
        return_value=SimpleNamespace(x=PLACE_LNG, y=PLACE_LAT),
    ):
        return asyncio.run(submit_visit(session, "u1", place_id, readings))


def test_visit_within_50m_and_30m_accuracy_succeeds():
    session = _FakeSession(place=_place())
    result = _run(session, _readings())
    assert result.already_today is False
    assert result.xp_awarded == 6  # XP_REWARD[PLACE_VISIT]
    assert len(session.added) == 2  # PlaceVisit + XpLedger
    assert session.commits == 2  # 방문 저장 커밋 + award_xp 커밋


def test_visit_over_50m_rejected():
    session = _FakeSession(place=_place())
    # 0.001도 ≈ 111m — 50m를 확실히 넘는 오프셋
    with pytest.raises(TooFarFromStoreError):
        _run(session, _readings(lat=PLACE_LAT + 0.001))


def test_visit_accuracy_over_30m_rejected():
    session = _FakeSession(place=_place())
    with pytest.raises(LowGpsAccuracyVisitError):
        _run(session, _readings(accuracy=31.0))


def test_visit_place_not_found():
    session = _FakeSession(place=None)
    with pytest.raises(PlacePublicNotFoundError):
        _run(session, _readings())


def test_visit_requires_exactly_two_readings():
    session = _FakeSession(place=_place())
    with pytest.raises(InvalidVisitReadingsError):
        _run(session, _readings()[:1])


def test_visit_rejects_identical_cached_timestamps():
    # 서로 다른 시점의 측정 2회를 요구한다(§7) — 같은 timestamp면 캐시 좌표
    # 재사용으로 간주해 거부.
    session = _FakeSession(place=_place())
    ts = datetime.now(UTC)
    readings = [
        VisitReading(lat=PLACE_LAT, lng=PLACE_LNG, accuracy_m=10.0, client_timestamp=ts),
        VisitReading(lat=PLACE_LAT, lng=PLACE_LNG, accuracy_m=10.0, client_timestamp=ts),
    ]
    with pytest.raises(InvalidVisitReadingsError):
        _run(session, readings)


def test_visit_rejects_future_timestamp():
    session = _FakeSession(place=_place())
    future = datetime.now(UTC) + timedelta(minutes=5)
    with pytest.raises(StaleLocationReadingError):
        _run(session, _readings(base_ts=future))


def test_visit_rejects_stale_timestamp():
    session = _FakeSession(place=_place())
    old = datetime.now(UTC) - timedelta(minutes=30)
    with pytest.raises(StaleLocationReadingError):
        _run(session, _readings(base_ts=old))


def test_visit_already_today_awards_no_xp():
    session = _FakeSession(place=_place(), existing_visit=object(), visit_count=3)
    result = _run(session, _readings())
    assert result.already_today is True
    assert result.xp_awarded == 0
    assert session.commits == 0  # PlaceVisit을 새로 저장하지 않는다
    assert result.visit_count == 3


def test_visit_concurrent_race_returns_already_today():
    # 동시 요청으로 유니크 인덱스에 걸리는 경우(§14) — IntegrityError를 잡아
    # 롤백 후 already_today로 응답, XP는 지급하지 않는다.
    session = _FakeSession(place=_place(), visit_count=2, fail_first_commit=True)
    result = _run(session, _readings())
    assert result.already_today is True
    assert result.xp_awarded == 0
    assert session.rollbacks == 1


def test_visit_different_day_is_independent():
    # visit_date가 오늘 기준이라, 다른 날짜엔 항상 새 방문으로 취급된다 —
    # 여기서는 "오늘 기존 방문 없음" 케이스가 정상적으로 성공하는지만 재확인한다
    # (KST 날짜 자체의 하루 넘김 계산은 streak.py의 _to_kst_date와 동일 로직 재사용).
    session = _FakeSession(place=_place(), existing_visit=None, visit_count=1)
    result = _run(session, _readings())
    assert result.already_today is False
    assert result.visit_count == 2
