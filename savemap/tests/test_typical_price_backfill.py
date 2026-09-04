import asyncio
from unittest.mock import AsyncMock

from app.domain.enums import SourceType
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.typical_price_backfill import backfill_typical_prices


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """첫 execute는 항상 메인 select(대상 메뉴 목록), 두 번째 execute는
    _load_existing_estimates(기존 캐시 로드) — 순서가 고정이라 큐로 흉내낸다.
    cache_rows를 안 주면 빈 캐시(전부 새로 추정)로 시작한다."""

    def __init__(self, rows, cache_rows=()):
        self._queue = [_Result(rows), _Result(list(cache_rows))]
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        return self._queue.pop(0)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _item(id_=1, name="김치찌개", normalized_name="김치찌개", ai_typical_price=None):
    return MenuItem(
        id=id_,
        place_id=1,
        name=name,
        normalized_name=normalized_name,
        price=8000.0,
        source=SourceType.S1_PUBLIC,
        ai_typical_price=ai_typical_price,
    )


def _place(address="충남 아산시"):
    return Place(id=1, name="가게", address=address, geom="fake-geom")


class _FakeClient:
    """배치 추정(2026-09-04)으로 바뀐 인터페이스를 흉내낸다 — 호출 수를 줄이려고
    (메뉴명, 지역) 묶음을 한 번에 넘기고 {인덱스: 가격}을 돌려받는다.
    prices=None이면 모든 항목을 같은 price로, dict면 인덱스별로 답한다
    (빈 dict = 전부 추정 실패)."""

    def __init__(self, price=9000.0, raise_exc=None, prices=None):
        self._price = price
        self._raise_exc = raise_exc
        self._prices = prices
        self.estimate_typical_prices_batch = AsyncMock(side_effect=self._call)

    async def _call(self, items):
        if self._raise_exc:
            raise self._raise_exc
        if self._prices is not None:
            return dict(self._prices)
        return {i: self._price for i in range(len(items))}


# --- backfill_typical_prices: 배치/캐시/페이지네이션 ---


def test_estimates_and_saves_price():
    item = _item()
    session = _FakeSession([(item, _place())])
    client = _FakeClient(price=9000.0)
    result = asyncio.run(backfill_typical_prices(session, limit=10, client=client))

    assert result["estimated"] == 1
    assert result["reused_from_cache"] == 0
    assert result["scanned"] == 1
    assert result["done"] is True
    assert item.ai_typical_price == 9000.0
    assert session.commits == 1
    assert session.rollbacks == 0
    client.estimate_typical_prices_batch.assert_awaited_once_with([("김치찌개", "충남")])


def test_reuses_existing_estimate_for_same_name_and_region_without_calling_api():
    item = _item(id_=2, normalized_name="김치찌개")
    # 기존 캐시에 이미 (김치찌개, 충남) 조합 추정치가 있다.
    session = _FakeSession(
        rows=[(item, _place(address="충남 아산시"))],
        cache_rows=[("김치찌개", "충남 아산시", 8500.0)],
    )
    client = _FakeClient()
    result = asyncio.run(backfill_typical_prices(session, limit=10, client=client))

    assert result["reused_from_cache"] == 1
    assert result["estimated"] == 0
    assert item.ai_typical_price == 8500.0
    client.estimate_typical_prices_batch.assert_not_awaited()


def test_different_region_does_not_reuse_cache():
    item = _item(id_=2, normalized_name="김치찌개")
    session = _FakeSession(
        rows=[(item, _place(address="서울 강남구"))],
        cache_rows=[("김치찌개", "충남 아산시", 8500.0)],  # 다른 지역 캐시
    )
    client = _FakeClient(price=11000.0)
    result = asyncio.run(backfill_typical_prices(session, limit=10, client=client))

    assert result["reused_from_cache"] == 0
    assert result["estimated"] == 1
    assert item.ai_typical_price == 11000.0


def test_dry_run_does_not_commit():
    item = _item()
    session = _FakeSession([(item, _place())])
    client = _FakeClient(price=9000.0)
    result = asyncio.run(backfill_typical_prices(session, limit=10, dry_run=True, client=client))

    assert result["estimated"] == 1
    assert session.rollbacks == 1
    assert session.commits == 0
    assert item.ai_typical_price is None  # dry_run이라 실제로는 안 붙음


def test_partial_batch_response_only_fills_answered_items():
    """배치 응답에 일부 항목이 빠져도(모델이 null을 주거나 아예 누락) 나머지는
    정상 저장돼야 한다 — 빠진 자리를 임의의 값으로 채우면 안 된다."""
    item1, item2 = _item(id_=1), _item(id_=2, name="제육볶음", normalized_name="제육볶음")
    session = _FakeSession([(item1, _place()), (item2, _place())])
    # 0번(김치찌개)은 응답에 없고 1번(제육볶음)만 값이 왔다.
    client = _FakeClient(prices={1: 12000.0})
    result = asyncio.run(backfill_typical_prices(session, limit=10, client=client))

    assert result["failed"] == 1
    assert result["estimated"] == 1
    assert item1.ai_typical_price is None
    assert item2.ai_typical_price == 12000.0


def test_batch_call_failure_does_not_crash_and_counts_all_as_failed():
    """묶음 호출 자체가 터져도(네트워크/한도) 예외가 밖으로 나가면 안 된다 —
    관리자 페이지의 반복 호출 루프가 통째로 멈춘다."""
    item1, item2 = _item(id_=1), _item(id_=2, name="제육볶음", normalized_name="제육볶음")
    session = _FakeSession([(item1, _place()), (item2, _place())])
    client = _FakeClient(raise_exc=RuntimeError("boom"))
    result = asyncio.run(backfill_typical_prices(session, limit=10, client=client))

    assert result["failed"] == 2
    assert result["estimated"] == 0
    assert item1.ai_typical_price is None
    assert item2.ai_typical_price is None


def test_none_response_counts_as_failed():
    session = _FakeSession([(_item(), _place())])
    client = _FakeClient(prices={})  # 모델이 null로 답해 아무 인덱스도 안 온 경우
    result = asyncio.run(backfill_typical_prices(session, limit=10, client=client))
    assert result["failed"] == 1
    assert result["estimated"] == 0


def test_next_offset_and_done_when_batch_smaller_than_limit():
    session = _FakeSession([(_item(id_=5), _place())])
    client = _FakeClient()
    result = asyncio.run(backfill_typical_prices(session, limit=10, client=client))
    assert result["next_offset"] == 6
    assert result["done"] is True


def test_not_done_when_batch_equals_limit():
    session = _FakeSession([(_item(id_=1), _place()), (_item(id_=2), _place())])
    client = _FakeClient()
    result = asyncio.run(backfill_typical_prices(session, limit=2, client=client))
    assert result["done"] is False
    assert result["next_offset"] == 3


def test_empty_batch_is_done():
    session = _FakeSession([])
    client = _FakeClient()
    result = asyncio.run(backfill_typical_prices(session, limit=10, client=client))
    assert result == {
        "offset": 0, "dry_run": False,
        "scanned": 0, "estimated": 0, "reused_from_cache": 0, "failed": 0,
        "next_offset": 0, "done": True,
    }
