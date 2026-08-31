from app.domain.enums import Category, Layer
from app.domain.menu_item import MenuItem
from app.engine.models import OfferCandidate
from app.engine.ranker import RankedOffer
from app.engine.result_assembly import build_search_result_item
from app.engine.savings_calculator import calculate_savings


def _ranked(layer: Layer, menu_item_id: int | None = None, ai_one_line: str | None = None) -> RankedOffer:
    candidate = OfferCandidate(
        offer_id=1,
        place_id=1,
        place_name="타임세일 매장",
        category=Category.DISCOUNT,
        layer=layer,
        distance_m=100.0,
        base_price=10000,
        lat=36.99,
        lng=127.11,
        store_discount=5000,
        menu_item_id=menu_item_id,
        ai_one_line=ai_one_line,
    )
    return RankedOffer(candidate=candidate, breakdown=calculate_savings(candidate), score=0.8)


# --- FLASH 배지(2026-08-18, "마감임박 긴급성 되살리기") --- 프론트가 마감
# 카운트다운을 보여줄지 판단하려면 layer가 API 응답에 그대로 실려야 한다 —
# 예전엔 OfferCandidate.layer가 있어도 SearchResultItem으로 조립하는 과정에서
# 누락돼 있었다(값 자체는 항상 있었는데 그냥 안 옮겼다).


def test_flash_layer_passes_through_to_result_item():
    item = build_search_result_item(_ranked(Layer.FLASH), menu_items_by_place={})
    assert item.layer == Layer.FLASH


def test_regular_layer_passes_through_to_result_item():
    item = build_search_result_item(_ranked(Layer.REGULAR), menu_items_by_place={})
    assert item.layer == Layer.REGULAR


# --- 대표메뉴는 절약률 계산에 쓰인 바로 그 메뉴여야 한다(2026-08-22) — 예전엔
# 연결이 끊기면 "가장 먼저 등록된 메뉴"로 조용히 폴백해서, 카드에 뜬 대표메뉴
# 가격과 실제 절약률 계산 근거가 다를 수 있었다. ---


def test_signature_menu_matches_the_menu_used_for_savings_calc():
    place_items = [
        MenuItem(id=1, place_id=1, name="된장찌개", price=7000.0),
        MenuItem(id=2, place_id=1, name="냉삼", price=8000.0),
        MenuItem(id=3, place_id=1, name="김치찌개", price=7500.0),
    ]
    item = build_search_result_item(
        _ranked(Layer.REGULAR, menu_item_id=2), menu_items_by_place={1: place_items}
    )
    assert item.signature_menu.name == "냉삼"
    assert item.signature_menu.price == 8000.0


def test_signature_menu_is_none_when_the_linked_menu_item_is_gone():
    # 링크가 끊긴 경우(메뉴 삭제 등) 엉뚱한 메뉴를 대표로 세우느니 아무것도 안 보여준다.
    place_items = [MenuItem(id=1, place_id=1, name="된장찌개", price=7000.0)]
    item = build_search_result_item(
        _ranked(Layer.REGULAR, menu_item_id=999), menu_items_by_place={1: place_items}
    )
    assert item.signature_menu is None


# --- AI 활용 확대 안건 D(2026-08-31) — 관리자 배치가 캐시해둔 ai_one_line이
# 있으면 그걸 쓰고, 출처(one_line_source)를 감추지 않는다. ---


def test_ai_one_line_overrides_template_and_marks_source_ai():
    item = build_search_result_item(
        _ranked(Layer.REGULAR, ai_one_line="주변보다 저렴한 곳이에요."), menu_items_by_place={}
    )
    assert item.report.one_line == "주변보다 저렴한 곳이에요."
    assert item.report.one_line_source == "ai"


def test_no_ai_one_line_falls_back_to_template_source():
    item = build_search_result_item(_ranked(Layer.REGULAR, ai_one_line=None), menu_items_by_place={})
    assert item.report.one_line_source == "template"
    assert item.report.one_line != ""  # savings_report.py의 결정론적 문구가 그대로 옴


def test_signature_menu_falls_back_to_first_when_offer_has_no_menu_item():
    # 메뉴에서 파생되지 않은 오퍼(사장님 직접 등록 할인 등)만 이 폴백을 쓴다.
    place_items = [
        MenuItem(id=1, place_id=1, name="된장찌개", price=7000.0),
        MenuItem(id=2, place_id=1, name="냉삼", price=8000.0),
    ]
    item = build_search_result_item(
        _ranked(Layer.REGULAR, menu_item_id=None), menu_items_by_place={1: place_items}
    )
    assert item.signature_menu.name == "된장찌개"
