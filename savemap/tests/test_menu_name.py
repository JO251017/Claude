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


def test_menu_extraction_prompt_covers_receipts_and_unit_price():
    """영수증 제보 경로가 프롬프트에서 조용히 빠지지 않게 고정한다.

    메뉴판은 가게 안에서 대놓고 찍어야 해서 심리적 장벽이 크고, 영수증은 이미 손에
    있다 — 가격을 실제로 모으려면 영수증 쪽이 현실적인 경로다. 그리고 영수증은
    "수량 × 단가 = 금액"이라, 합계를 단가로 읽으면 가격이 부풀려진다.
    """
    from app.integrations.gemini import _MENU_EXTRACTION_PROMPT

    assert "영수증" in _MENU_EXTRACTION_PROMPT
    assert "단가" in _MENU_EXTRACTION_PROMPT
    # 합계·부가세 같은 메뉴 아닌 줄이 메뉴로 들어오면 안 된다.
    assert "부가세" in _MENU_EXTRACTION_PROMPT


def test_backfill_only_updates_rows_whose_normalized_name_is_stale():
    """정규화 규칙이 바뀐 뒤 재실행해도, 이미 맞는 행은 다시 안 건드려야 한다
    (admin.backfill_menu_normalized_names가 이 판정으로 updated 카운트를 센다)."""
    from app.engine.menu_name import normalize_menu_name

    item = MenuItem(place_id=1, name="아메리카노 (ICE)", price=3500)
    # 정상 경로(모델 validates)로 이미 맞게 채워져 있다.
    assert item.normalized_name == normalize_menu_name(item.name)

    # SQL Editor로 컬럼만 추가된 "레거시" 행을 흉내낸다 — normalized_name이 비어 있다.
    item.normalized_name = ""
    correct = normalize_menu_name(item.name)
    assert item.normalized_name != correct  # backfill 대상으로 판정돼야 함

    item.normalized_name = correct
    assert item.normalized_name == correct  # 재실행 시 더 건드릴 게 없어야 함


# --- 표기 변형 통일(2026-09-03) --- 운영 DB에서 같은 것이 표기만 달라 갈라져
# 있는 걸 확인하고 추가했다(커트/컷트가 남남, 짜장면/자장면이 남남). 병합 후
# 3km 반경 실측 비교 가능 비율이 25.8% → 31.0%로 올랐다.


def test_spelling_variants_merge_to_one_name():
    assert normalize_menu_name("컷트") == normalize_menu_name("커트")
    assert normalize_menu_name("자장면") == normalize_menu_name("짜장면")
    assert normalize_menu_name("돈가스") == normalize_menu_name("돈까스")
    assert normalize_menu_name("퍼머") == normalize_menu_name("파마")
    assert normalize_menu_name("남자커트") == normalize_menu_name("남성커트")


def test_variant_merge_runs_after_other_normalization_steps():
    """괄호·크기 접미사를 떼고 난 뒤의 형태에도 통일이 걸려야 한다 —
    "컷트(중)"까지 커트로 모이지 않으면 표를 붙인 의미가 절반으로 준다."""
    assert normalize_menu_name("컷트(중)") == "커트"
    assert normalize_menu_name("컷 트") == "커트"


def test_cut_of_meat_variants_are_not_merged():
    """부위·두께가 다르면 가격대도 다르다 — 표기 통일표(_SYNONYMS)에 삼겹살
    계열을 넣지 않은 이유를 고정해둔다(기존 test_different_dishes_are_never_merged가
    다루는 재료 차이와 별개 축)."""
    assert normalize_menu_name("대패삼겹살") != normalize_menu_name("삼겹살")
    assert normalize_menu_name("생삼겹살") != normalize_menu_name("대패삼겹살")
