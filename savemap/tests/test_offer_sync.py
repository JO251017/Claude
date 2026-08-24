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


def test_benchmark_metadata_recorded_even_when_not_cheaper():
    # "비교는 했는데 안 싸더라"도 유효한 재계산 결과다 — 재동기화가 언제 마지막으로
    # 이 오퍼를 훑었는지는 benchmark_source가 None이어도 알아야 한다.
    cmp = MenuPriceComparison(
        menu_item_id=1, name="냉삼", store_price=8000.0, place_id=1,
        region_average=9000.0, region_median=9000.0, sample_count=4,
        savings_amount=None, savings_rate=None, reliable=True,
        benchmark_source=None, benchmark_price=None,
    )
    session = _run_sync(cmp)
    offer = session.added[0]
    assert offer.benchmark_sample_count == 4
    assert offer.benchmark_synced_at is not None


def test_commit_false_does_not_commit():
    # 재동기화 배치는 여러 건을 한 트랜잭션에 묶는다 — commit=False면 호출부가
    # 알아서 커밋할 때까지 이 함수는 커밋하면 안 된다.
    place = Place(id=1, name="가게", address="주소")
    item = MenuItem(id=1, place_id=1, name="냉삼", price=8000.0)
    session = _FakeSession()
    cmp = MenuPriceComparison(
        menu_item_id=1, name="냉삼", store_price=8000.0, place_id=1,
        region_average=None, region_median=None, sample_count=0,
        savings_amount=None, savings_rate=None, reliable=False,
        benchmark_source=None, benchmark_price=None,
    )
    with (
        patch("app.engine.offer_sync.compare_menu_item", new=AsyncMock(return_value=cmp)),
        patch("app.engine.offer_sync.to_shape", return_value=SimpleNamespace(x=127.0, y=37.0)),
    ):
        asyncio.run(offer_sync.sync_menu_offer(session, place, item, commit=False))
    assert session.committed == 0
    assert len(session.added) == 1


def test_existing_offer_injected_skips_select():
    # 배치가 IN절로 미리 조회해 넘기면, 이 함수는 건당 SELECT를 또 던지면 안 된다
    # (existing_offer=_UNSET일 때만 조회하는 게 계약).
    place = Place(id=1, name="가게", address="주소")
    item = MenuItem(id=1, place_id=1, name="냉삼", price=8000.0)

    class _NoExecuteSession(_FakeSession):
        async def execute(self, *a, **kw):
            raise AssertionError("existing_offer가 주어졌으면 execute를 호출하면 안 된다")

    session = _NoExecuteSession()
    existing = SimpleNamespace(
        title="", base_price=None, store_discount=None,
        benchmark_source=None, benchmark_sample_count=None, benchmark_synced_at=None,
    )
    cmp = MenuPriceComparison(
        menu_item_id=1, name="냉삼", store_price=8000.0, place_id=1,
        region_average=None, region_median=None, sample_count=0,
        savings_amount=None, savings_rate=None, reliable=False,
        benchmark_source=None, benchmark_price=None,
    )
    with (
        patch("app.engine.offer_sync.compare_menu_item", new=AsyncMock(return_value=cmp)),
        patch("app.engine.offer_sync.to_shape", return_value=SimpleNamespace(x=127.0, y=37.0)),
    ):
        asyncio.run(
            offer_sync.sync_menu_offer(session, place, item, commit=False, existing_offer=existing)
        )
    assert session.added == []  # 새로 add된 게 아니라 기존 객체(existing)를 갱신했어야 함
