import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.offer_resync import resync_offers


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    """join 쿼리(select(MenuItem, Place))는 .all()을 바로 쓰고, 기존 오퍼 IN 쿼리는
    .scalars().all()을 쓴다 — 둘 다 이 하나로 흉내낸다."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return _Scalars(self._rows)


class _FakeSession:
    """첫 execute 호출은 join 쿼리(MenuItem, Place) 결과, 두 번째는 기존 Offer IN
    쿼리 결과를 순서대로 돌려준다 — resync_offers가 이 순서로만 쿼리를 던진다."""

    def __init__(self, batch_rows, existing_offers=()):
        self._batch_rows = batch_rows
        self._existing_offers = list(existing_offers)
        self.execute_calls = 0
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _Result(self._batch_rows)
        return _Result(self._existing_offers)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _item_place(item_id, place_id=10, geom="fake-geom", address="충남 아산시"):
    item = MenuItem(id=item_id, place_id=place_id, name="냉삼", price=8000.0)
    place = Place(id=place_id, name="가게", address=address, geom=geom)
    return item, place


def _run(session, **kwargs):
    with patch(
        "app.engine.offer_resync.sync_menu_offer",
        new=AsyncMock(return_value=SimpleNamespace(benchmark_source=kwargs.pop("cmp_source", "region"))),
    ) as mocked:
        result = asyncio.run(resync_offers(session, **kwargs))
    return result, mocked


def test_resync_pages_and_marks_done_when_batch_smaller_than_limit():
    rows = [_item_place(1), _item_place(2), _item_place(3)]
    session = _FakeSession(rows)
    result, mocked = _run(session, limit=500)

    assert result["scanned"] == 3
    assert result["resynced"] == 3
    assert result["next_offset"] == 4  # 마지막 menu_item.id(3) + 1
    assert result["done"] is True
    assert mocked.await_count == 3


def test_resync_not_done_when_batch_equals_limit():
    rows = [_item_place(1), _item_place(2)]
    session = _FakeSession(rows)
    result, _ = _run(session, limit=2)
    assert result["done"] is False
    assert result["next_offset"] == 3


def test_resync_skips_places_without_geom():
    rows = [_item_place(1, geom=None), _item_place(2)]
    session = _FakeSession(rows)
    result, mocked = _run(session)

    assert result["skipped_no_geom"] == 1
    assert result["resynced"] == 1
    assert mocked.await_count == 1  # geom 없는 항목은 sync_menu_offer 자체를 안 부름


def test_resync_records_benchmark_transitions_and_changed_count():
    rows = [_item_place(1)]
    existing = SimpleNamespace(menu_item_id=1, benchmark_source="ai")
    session = _FakeSession(rows, existing_offers=[existing])
    result, _ = _run(session, cmp_source="region")

    assert result["changed"] == 1
    assert result["benchmark_transitions"] == {"ai->region": 1}
    assert result["source_after"] == {"region": 1}


def test_resync_unchanged_when_benchmark_source_does_not_change():
    rows = [_item_place(1)]
    existing = SimpleNamespace(menu_item_id=1, benchmark_source="region")
    session = _FakeSession(rows, existing_offers=[existing])
    result, _ = _run(session, cmp_source="region")

    assert result["changed"] == 0
    assert result["benchmark_transitions"] == {"region->region": 1}


def test_resync_no_existing_offer_treated_as_none_before():
    rows = [_item_place(1)]
    session = _FakeSession(rows, existing_offers=[])  # 이 배치 안에 오퍼가 아예 없음
    result, _ = _run(session, cmp_source="gov")

    assert result["benchmark_transitions"] == {"none->gov": 1}


def test_one_item_failing_does_not_block_the_rest():
    rows = [_item_place(1), _item_place(2)]
    session = _FakeSession(rows)
    with patch(
        "app.engine.offer_resync.sync_menu_offer",
        new=AsyncMock(side_effect=[RuntimeError("boom"), SimpleNamespace(benchmark_source="region")]),
    ):
        result = asyncio.run(resync_offers(session))

    assert result["resynced"] == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["menu_item_id"] == 1
    assert session.rollbacks >= 1  # 실패한 행 직후 롤백


def test_dry_run_rolls_back_instead_of_committing():
    rows = [_item_place(1)]
    session = _FakeSession(rows)
    result, _ = _run(session, dry_run=True)

    assert result["dry_run"] is True
    assert session.commits == 0
    assert session.rollbacks == 1


def test_not_dry_run_commits_once_for_small_batch():
    rows = [_item_place(1)]
    session = _FakeSession(rows)
    _run(session, dry_run=False)
    assert session.commits == 1
    assert session.rollbacks == 0


def test_empty_batch_returns_done_without_querying_offers():
    session = _FakeSession(batch_rows=[])
    result = asyncio.run(resync_offers(session, offset=999))

    assert result == {
        "region": None, "offset": 999, "dry_run": False,
        "scanned": 0, "resynced": 0, "skipped_no_geom": 0, "failed": [],
        "changed": 0, "benchmark_transitions": {}, "source_after": {},
        "next_offset": 999, "done": True,
    }
    assert session.execute_calls == 1  # 오퍼 IN 쿼리는 아예 안 날림
