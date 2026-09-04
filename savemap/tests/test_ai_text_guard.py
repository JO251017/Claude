from app.engine.ai_text_guard import extract_numbers, has_unapproved_numbers


def test_extract_numbers_normalizes_commas():
    assert extract_numbers("8,000원 정도예요") == {"8000"}


def test_extract_numbers_finds_multiple():
    assert extract_numbers("8곳과 비교해 23% 저렴해요") == {"8", "23"}


def test_extract_numbers_empty_when_no_digits():
    assert extract_numbers("숫자가 하나도 없는 문장이에요") == set()


def test_no_unapproved_numbers_when_all_match():
    assert has_unapproved_numbers("8곳과 비교했어요", {"8"}) is False


def test_unapproved_number_detected():
    # 실사용을 가정한 핵심 케이스: AI가 준 사실에 없는 숫자(23%)를 지어낸 경우.
    assert has_unapproved_numbers("23% 더 저렴해요", {"8"}) is True


def test_comma_formatted_number_still_matches_allowed():
    # "8000"으로 승인했는데 AI가 "8,000"으로 콤마를 넣어 써도 같은 숫자로 인정한다
    # — 표기 차이는 허용, 새 숫자만 막는다.
    assert has_unapproved_numbers("8,000원이에요", {"8000"}) is False


def test_no_numbers_and_no_allowed_is_fine():
    assert has_unapproved_numbers("가격 경쟁력이 좋은 곳이에요", set()) is False
