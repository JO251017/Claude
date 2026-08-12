import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine import offer_sync
from app.engine.price_comparison import MenuPriceComparison


class _FakeResult:
    def scalar_one_or_none(self):
        return None  # 항상 "기존 오퍼 없음" 취급 → 새 Offer 생성 경로를 검증


class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = 0

    async def execute(self, *a, **kw):
        # sync_menu_offer가 직접 던지는 existing_offer 조회만 여기로 온다 —
        # compare_menu_item 자체는 테스트에서 패치해서 이 세션까지 안 내려온다.
        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _run_sync(cmp: MenuPriceComparison):
    place = Place(id=1, name="가게", address="주소")
    item = MenuItem(id=1, place_id=1, name="냉삼", price=8000.0)
    session = _FakeSession()

    with (
        patch("app.engine.offer_sync.compare_menu_item", new=AsyncMock(return_value=cmp)),
        patch("app.engine.offer_sync.to_shape", return_value=SimpleNamespace(x=127.0, y=37.0)),
    ):
        asyncio.run(offer_sync.sync_menu_offer(session, place, item))
    return session


def test_ai_estimated_savings_are_tagged_with_ai_benchmark_source():
    # 실측 표본이 없어 AI 추정 통상가로 절약을 계산한 경우, Offer에도 "ai"가 그대로
    # 남아야 검색 응답이 이걸 실측처럼 말하지 않는다.
    cmp = MenuPriceComparison(
        menu_item_id=1, name="냉삼", store_price=8000.0, place_id=1,
        region_average=None, region_median=None, sample_count=0,
        savings_amount=1000.0, savings_rate=11.1, reliable=False,
        benchmark_source="ai", benchmark_price=9000.0,
    )
    session = _run_sync(cmp)
    assert len(session.added) == 1
    offer = session.added[0]
    assert offer.benchmark_source == "ai"
    assert offer.store_discount == 1000.0
    assert "AI 추정" in offer.title


def test_region_estimated_savings_are_tagged_with_region_benchmark_source():
    cmp = MenuPriceComparison(
        menu_item_id=1, name="냉삼", store_price=8000.0, place_id=1,
        region_average=9500.0, region_median=9500.0, sample_count=3,
        savings_amount=1500.0, savings_rate=15.8, reliable=True,
        benchmark_source="region", benchmark_price=9500.0,
    )
    session = _run_sync(cmp)
    offer = session.added[0]
    assert offer.benchmark_source == "region"


def test_no_savings_leaves_benchmark_source_none():
    # 비교 기준이 있어도 이 가게가 더 싸지 않으면(cheaper=False) 할인 자체가 없으니
    # benchmark_source도 지어내지 않고 None으로 둔다.
    cmp = MenuPriceComparison(
        menu_item_id=1, name="냉삼", store_price=8000.0, place_id=1,
        region_average=None, region_median=None, sample_count=0,
        savings_amount=None, savings_rate=None, reliable=False,
        benchmark_source=None, benchmark_price=None,
    )
    session = _run_sync(cmp)
    offer = session.added[0]
    assert offer.benchmark_source is None
    assert offer.store_discount == 0.0
