from app.domain.enums import Category, Layer, RouteActivity
from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.rule_filter import rule_filter


def _row(offer_id: int, category_name: str | None, category: Category = Category.DISCOUNT):
    offer = Offer(id=offer_id, place_id=offer_id, category=category, layer=Layer.REGULAR, title="t")
    place = Place(id=offer_id, name=f"place{offer_id}", category_name=category_name)
    return (offer, place, 100.0)


def test_activities_filter_keeps_only_matching_activity():
    rows = [
        _row(1, "일반음식점 > 한식"),  # dining
        _row(2, "음식점 > 카페 > 커피전문점"),  # cafe
        _row(3, "숙박업"),  # 미분류
    ]
    result = rule_filter(rows, activities=[RouteActivity.DINING])
    assert [o.id for o, _, _ in result] == [1]


def test_activities_filter_supports_multiple_activities():
    rows = [
        _row(1, "일반음식점 > 한식"),
        _row(2, "음식점 > 카페 > 커피전문점"),
        _row(3, "휴게음식점 > 제과점영업"),
    ]
    result = rule_filter(rows, activities=[RouteActivity.CAFE, RouteActivity.DESSERT])
    assert {o.id for o, _, _ in result} == {2, 3}


def test_empty_activities_list_does_not_filter_anything():
    # 빈 리스트(활동 미선택)는 기존 /search 동작과 동일하게 아무 것도 안 거른다.
    rows = [_row(1, "일반음식점 > 한식"), _row(2, None)]
    result = rule_filter(rows, activities=[])
    assert len(result) == 2


def test_activities_filter_excludes_unclassified_places():
    # 활동을 지정했는데 뭔지 모르는(None) 매장은 "혹시 몰라 포함"이 아니라 정직하게
    # 제외한다.
    rows = [_row(1, "숙박업")]
    result = rule_filter(rows, activities=[RouteActivity.DINING])
    assert result == []


def test_category_and_activities_filters_combine():
    rows = [
        _row(1, "일반음식점 > 한식", category=Category.FREE_PARKING),
        _row(2, "일반음식점 > 한식", category=Category.DISCOUNT),
    ]
    result = rule_filter(rows, category=Category.FREE_PARKING, activities=[RouteActivity.DINING])
    assert [o.id for o, _, _ in result] == [1]


# --- FLASH(마감임박 타임세일) 검색 노출(2026-08-18, "핵심 콘셉트 강화") ---
# 예전 기본값(mvp_only=True)은 FLASH 레이어를 통째로 걸러냈다 — 사장님이 실제
# TTL 있는 타임세일을 등록해도 지도에 영원히 안 떴다. 기본값을 뒤집었으니 이제
# 기본 호출(= /search가 쓰는 그대로)에서 FLASH도 나와야 한다.


def test_flash_layer_included_by_default():
    offer = Offer(id=1, place_id=1, category=Category.DISCOUNT, layer=Layer.FLASH, title="타임세일")
    place = Place(id=1, name="place1")
    result = rule_filter([(offer, place, 50.0)])
    assert [o.id for o, _, _ in result] == [1]


def test_mvp_only_true_still_excludes_flash_when_explicitly_requested():
    # 옛 동작이 필요한 호출부가 나중에 생기면 여전히 켤 수 있다는 것만 확인.
    offer = Offer(id=1, place_id=1, category=Category.DISCOUNT, layer=Layer.FLASH, title="타임세일")
    place = Place(id=1, name="place1")
    result = rule_filter([(offer, place, 50.0)], mvp_only=True)
    assert result == []
