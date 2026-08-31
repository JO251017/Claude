import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.domain.price_history import PriceHistory
from app.engine import offer_sync
from app.engine.price_comparison import MenuPriceComparison

_CMP = MenuPriceComparison(
    menu_item_id=1, name="냉삼", store_price=8000.0, place_id=1,
    region_average=None, region_median=None, sample_count=0,
    savings_amount=None, savings_rate=None, reliable=False,
    benchmark_source=None, benchmark_price=None,
)


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """execute()가 항상 no-op(빈 Offer 조회)을 돌려주는, existing_offer/
    current_price_history를 둘 다 주입해서 이 세션에 아예 안 닿게 만드는 용도."""

    def __init__(self):
        self.added = []
        self.committed = 0

    async def execute(self, *a, **kw):
        raise AssertionError("existing_offer/current_price_history를 주입했으면 execute를 호출하면 안 된다")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _run(item_price: float, current: PriceHistory | None):
    place = Place(id=1, name="가게", address="주소")
    item = MenuItem(id=1, place_id=1, name="냉삼", price=item_price)
    session = _FakeSession()
    existing_offer = SimpleNamespace(
        title="", base_price=None, store_discount=None,
        benchmark_source=None, benchmark_sample_count=None, benchmark_synced_at=None,
    )
    with (
        patch("app.engine.offer_sync.compare_menu_item", new=AsyncMock(return_value=_CMP)),
        patch("app.engine.offer_sync.to_shape", return_value=SimpleNamespace(x=127.0, y=37.0)),
    ):
        asyncio.run(
            offer_sync.sync_menu_offer(
                session,
                place,
                item,
                commit=False,
                existing_offer=existing_offer,
                current_price_history=current,
            )
        )
    return session


def test_first_ever_price_creates_initial_history_row():
    session = _run(8000.0, current=None)
    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, PriceHistory)
    assert row.price == 8000.0
    assert row.is_current is True
    assert row.valid_from is not None


def test_unchanged_price_does_not_create_a_new_row():
    current = PriceHistory(
        menu_item_id=1, place_id=1, price=8000.0, source_type=None,
        observed_at=datetime.now(UTC), valid_from=datetime.now(UTC), is_current=True,
    )
    session = _run(8000.0, current=current)
    assert session.added == []
    assert current.is_current is True  # 안 닫힘


def test_changed_price_closes_old_row_and_adds_new_one():
    current = PriceHistory(
        menu_item_id=1, place_id=1, price=8000.0, source_type=None,
        observed_at=datetime.now(UTC), valid_from=datetime.now(UTC), is_current=True,
    )
    session = _run(9000.0, current=current)

    assert current.is_current is False
    assert current.valid_to is not None
    assert len(session.added) == 1
    new_row = session.added[0]
    assert new_row.price == 9000.0
    assert new_row.is_current is True


def test_tiny_rounding_difference_is_treated_as_unchanged():
    current = PriceHistory(
        menu_item_id=1, place_id=1, price=8000.0, source_type=None,
        observed_at=datetime.now(UTC), valid_from=datetime.now(UTC), is_current=True,
    )
    session = _run(8000.005, current=current)
    assert session.added == []
