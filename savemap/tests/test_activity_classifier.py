from app.domain.enums import RouteActivity
from app.engine.activity_classifier import classify_activity


def test_classifies_dining_from_restaurant_registry_category():
    assert classify_activity("일반음식점 > 한식") == RouteActivity.DINING


def test_classifies_cafe_from_kakao_category():
    assert classify_activity("음식점 > 카페 > 커피전문점") == RouteActivity.CAFE


def test_classifies_dessert_from_bakery_keyword():
    assert classify_activity("휴게음식점 > 제과점영업") == RouteActivity.DESSERT


def test_returns_none_for_unmatched_category():
    # 실제로 뭔지 모르면 억지로 셋 중 하나로 지어내지 않고 None이어야 한다.
    assert classify_activity("숙박업") is None


def test_returns_none_for_missing_category_name():
    assert classify_activity(None) is None
    assert classify_activity("") is None


def test_dining_keyword_wins_over_cafe_when_both_present():
    # dining을 먼저 검사해서 두 키워드가 같이 들어간 문자열이 카페로 새지 않게 한다.
    assert classify_activity("일반음식점 > 카페") == RouteActivity.DINING
