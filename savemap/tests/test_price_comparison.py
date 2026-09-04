"""_region_prices의 자기표본 제외를 검증한다.

샌드박스에 실제 Postgres/PostGIS가 없어서, 쿼리가 자기 매장을 실제로 빼는지는
컴파일된 SQL 문자열로만 확인할 수 있다 — 그래서 쿼리 생성을 순수 함수로 뺐다
(app/engine/price_comparison.py의 _region_prices_stmt).
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.domain.menu_item import MenuItem
from app.engine.price_comparison import _region_prices_stmt, compare_menu_item


def _compiled(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_exclude_place_id_adds_the_filter():
    stmt = _region_prices_stmt("아메리카노", 37.0, 127.0, 3.0, exclude_place_id=42)
    assert "menu_item.place_id != 42" in _compiled(stmt)


def test_no_exclude_place_id_omits_the_filter():
    stmt = _region_prices_stmt("아메리카노", 37.0, 127.0, 3.0, exclude_place_id=None)
    assert "place_id !=" not in _compiled(stmt)


def _run_compare(region_prices: list[float]):
    """_region_prices 자체를 이웃 가격만 돌려주는 걸로 패치해, compare_menu_item이
    exclude_place_id를 실제로 넘기는지와 그 결과(표본=이웃 수)로 사다리를 매기는지를
    확인한다."""
    item = MenuItem(id=1, place_id=99, name="냉삼", price=8000.0)
    fake_region_prices = AsyncMock(return_value=region_prices)
    with (
        patch("app.engine.price_comparison._region_prices", new=fake_region_prices),
        patch("app.engine.price_comparison._government_stat", new=AsyncMock(return_value=None)),
    ):
        cmp = asyncio.run(compare_menu_item(None, item, lat=37.0, lng=127.0))
    return cmp, fake_region_prices


def test_compare_menu_item_passes_its_own_place_id_to_exclude():
    _, fake = _run_compare([9000.0])
    assert fake.await_args.kwargs["exclude_place_id"] == 99


def test_one_neighbor_is_no_longer_enough_for_reliable_with_old_semantics_but_now_is():
    # exclude_place_id 도입 이후, _region_prices가 돌려주는 리스트 자체가 이미
    # "이웃만"이므로 이웃 1곳(길이 1)은 MIN_RELIABLE_SAMPLE=2 미만 → region 승격 안 됨.
    # (예전엔 자기 자신이 섞여 있어서 이 리스트 길이가 2였던 상황과 대비된다.)
    cmp, _ = _run_compare([9000.0])
    assert cmp.sample_count == 1
    assert cmp.reliable is False
    assert cmp.benchmark_source != "region"


def test_two_neighbors_are_reliable_and_median_is_pure_neighbor_value():
    cmp, _ = _run_compare([8500.0, 9500.0])
    assert cmp.sample_count == 2
    assert cmp.reliable is True
    assert cmp.benchmark_source == "region"
    # 자기 가격(8000)이 안 섞였으므로 median은 순수 이웃 값 그대로다.
    assert cmp.region_median == 9000.0
    # 절약액도 이제 축소되지 않는다: 9000 - 8000 = 1000 (예전 버그는 이 절반이 나왔다).
    assert cmp.savings_amount == 1000.0
