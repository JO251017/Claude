"""비교 기준 사다리: 주변 실측 > 정부 통계(참가격) > AI 추정.

근거가 강한 쪽을 항상 먼저 써야 하고, 아래 등급으로는 위가 없을 때만 내려가야 한다.
이게 뒤집히면 앱이 "실측 반영"이라고 말하면서 실제로는 추정치를 보여주게 된다.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.domain.regional_price import RegionalPriceStat
from app.engine.price_comparison import compare_menu_item


def _menu_item(name: str = "칼국수", price: float = 7000.0, ai_price: float | None = None):
    item = MenuItem(place_id=1, name=name, price=price, ai_typical_price=ai_price)
    item.id = 10
    return item


def _run(item, region_prices, gov_stat, address="충청남도 아산시 배방읍 모산로 151-2"):
    place = Place(name="테스트식당", address=address)

    async def _fake_region_prices(*_args, **_kwargs):
        return region_prices

    async def _fake_get(_model, _pk):
        return place

    session = AsyncMock()
    session.get = _fake_get
    with (
        patch("app.engine.price_comparison._region_prices", new=_fake_region_prices),
        patch(
            "app.engine.price_comparison.get_regional_price",
            new=AsyncMock(return_value=gov_stat),
        ),
    ):
        return asyncio.run(compare_menu_item(session, item, lat=36.8, lng=127.1))


def test_region_measurements_win_over_government_stats():
    gov = RegionalPriceStat(dish="칼국수", region="충남", price=9200, survey_period="2026-07")
    cmp = _run(_menu_item(ai_price=8000), region_prices=[8500.0, 9000.0], gov_stat=gov)
    assert cmp.benchmark_source == "region"
    assert cmp.benchmark_price == 8750.0  # 중앙값


def test_government_stats_win_over_ai_estimate():
    # 예전엔 주변 표본이 없으면 곧장 AI 추정으로 떨어졌다. 이제 정부 조사값이 먼저다.
    gov = RegionalPriceStat(dish="칼국수", region="충남", price=9200, survey_period="2026-07")
    cmp = _run(_menu_item(ai_price=8000), region_prices=[], gov_stat=gov)
    assert cmp.benchmark_source == "gov"
    assert cmp.benchmark_price == 9200.0
    assert cmp.benchmark_period == "2026-07"
    assert cmp.savings_amount == 2200.0


def test_ai_estimate_is_the_last_resort():
    cmp = _run(_menu_item(ai_price=8000), region_prices=[], gov_stat=None)
    assert cmp.benchmark_source == "ai"
    assert cmp.benchmark_price == 8000.0


def test_no_benchmark_at_all_reports_none_rather_than_guessing():
    cmp = _run(_menu_item(ai_price=None), region_prices=[], gov_stat=None)
    assert cmp.benchmark_source is None
    assert cmp.savings_amount is None


def test_government_stat_skipped_when_address_has_no_sido():
    # 시도를 못 읽으면 엉뚱한 지역 평균과 비교하느니 AI 추정으로 내려간다.
    gov = RegionalPriceStat(dish="칼국수", region="충남", price=9200)
    cmp = _run(_menu_item(ai_price=8000), region_prices=[], gov_stat=gov, address="배방읍 모산로 1")
    assert cmp.benchmark_source == "ai"


def test_government_stat_skipped_for_items_outside_the_survey():
    # 참가격 외식비 8개 품목이 아니면 정부 통계 기준 자체가 없다.
    gov = RegionalPriceStat(dish="칼국수", region="충남", price=9200)
    cmp = _run(_menu_item(name="아메리카노", ai_price=4500), region_prices=[], gov_stat=gov)
    assert cmp.benchmark_source == "ai"
