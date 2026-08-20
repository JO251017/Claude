from app.domain.menu_item import MenuItem
from app.engine.menu_name import canonical_dish, normalize_menu_name


def test_whitespace_and_case_differences_collapse():
    assert normalize_menu_name(" 김치찌개 ") == normalize_menu_name("김치찌개")
    assert normalize_menu_name("바지락 칼국수") == normalize_menu_name("바지락칼국수")
    assert normalize_menu_name("ABC") == normalize_menu_name("abc")


def test_bracketed_notes_are_dropped():
    # 표기 부가정보일 뿐 다른 메뉴가 아니다 — 예전엔 이것 때문에 비교가 안 걸렸다.
    assert normalize_menu_name("아메리카노(ICE)") == normalize_menu_name("아메리카노")
    assert normalize_menu_name("제육볶음[특]") == normalize_menu_name("제육볶음")
    assert normalize_menu_name("칼국수(대)") == normalize_menu_name("칼국수")


def test_portion_suffixes_are_dropped():
    assert normalize_menu_name("삼겹살1인분") == normalize_menu_name("삼겹살")
    assert normalize_menu_name("자장면곱빼기") == normalize_menu_name("자장면")


def test_different_dishes_are_never_merged():
    # 정규화는 표기만 손본다. 재료·종류가 다른 메뉴를 합치면 값이 다른 것끼리
    # 비교하게 되고, 그건 없는 절약률을 만들어내는 것과 같다.
    assert normalize_menu_name("바지락칼국수") != normalize_menu_name("칼국수")
    assert normalize_menu_name("아이스아메리카노") != normalize_menu_name("아메리카노")
    assert normalize_menu_name("물냉면") != normalize_menu_name("비빔냉면")


def test_empty_or_symbol_only_names_do_not_collapse_together():
    # 전부 빈 문자열이 되면 서로 다른 메뉴가 같은 메뉴로 묶여버린다.
    assert normalize_menu_name("(대)") != normalize_menu_name("(소)")
    assert normalize_menu_name("") == ""


def test_canonical_dish_maps_to_government_survey_items():
    assert canonical_dish("바지락칼국수") == "칼국수"
    assert canonical_dish("물냉면") == "냉면"
    assert canonical_dish("짜장면") == "자장면"  # 표준어 표기로 통일
    assert canonical_dish("삼겹살 1인분") == "삼겹살"
    assert canonical_dish("김치찌개백반") == "김치찌개백반"


def test_canonical_dish_returns_none_outside_the_survey():
    # 정부 통계에 없는 품목까지 억지로 묶으면 기준이 없는데 있는 것처럼 보인다.
    assert canonical_dish("아메리카노") is None
    assert canonical_dish("돈까스") is None
    assert canonical_dish("") is None


def test_menu_item_fills_normalized_name_on_assignment():
    # 새 저장 경로가 생겨도 정규화를 잊어버릴 수 없게 모델이 직접 채운다.
    item = MenuItem(place_id=1, name="아메리카노 (ICE)", price=3500)
    assert item.normalized_name == "아메리카노"

    item.name = "카페라떼(HOT)"
    assert item.normalized_name == "카페라떼"
