from app.domain.enums import Category, Layer
from app.engine.models import OfferCandidate
from app.engine.ranker import RankedOffer
from app.engine.result_assembly import build_search_result_item
from app.engine.savings_calculator import calculate_savings


def _ranked(layer: Layer) -> RankedOffer:
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
