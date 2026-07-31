from app.sources.public_api.good_price import parse_price, parse_row


def test_parse_price_handles_real_world_formats():
    assert parse_price("9,000") == 9000.0
    assert parse_price("9000원") == 9000.0
    assert parse_price(" 12,500원~ ") == 12500.0
    assert parse_price(8000) == 8000.0
    assert parse_price("") is None
    assert parse_price(None) is None
    assert parse_price("가격문의") is None
    assert parse_price("50") is None  # 비현실적으로 낮은 값은 버림


def test_parse_row_full():
    row = {
        "업소명": "평택착한식당",
        "소재지도로명주소": "경기도 평택시 중앙로 1",
        "전화번호": "031-000-0000",
        "업종": "한식",
        "품목1": "김치찌개",
        "가격1": "8,000",
        "품목2": "된장찌개",
        "가격2": "7000원",
        "위도": "36.9921",
        "경도": "127.1125",
    }
    parsed = parse_row(row)
    assert parsed is not None
    assert parsed["name"] == "평택착한식당"
    assert parsed["menu_items"] == [("김치찌개", 8000.0), ("된장찌개", 7000.0)]
    assert abs(parsed["lat"] - 36.9921) < 1e-6


def test_parse_row_tolerates_spaced_column_names():
    row = {
        "업소명": "가게",
        "소재지 도로명 주소": "충남 천안시 1",
        "품목 1": "칼국수",
        "가격 1": "9,000",
        "위도": "36.8",
        "경도": "127.1",
    }
    parsed = parse_row(row)
    assert parsed is not None
    assert parsed["address"] == "충남 천안시 1"
    assert parsed["menu_items"] == [("칼국수", 9000.0)]


def test_parse_row_rejects_incomplete_rows():
    # 좌표 없음
    assert parse_row({"업소명": "가게", "품목1": "국밥", "가격1": "9000"}) is None
    # 메뉴 가격 없음
    assert parse_row({"업소명": "가게", "위도": "36.9", "경도": "127.1", "품목1": "국밥"}) is None
    # 한국 밖 좌표 (데이터 오류)
    assert (
        parse_row({"업소명": "가게", "위도": "3.69", "경도": "12.71", "품목1": "국밥", "가격1": "9000"})
        is None
    )


def test_parse_csv_bytes_cp949_and_utf8():
    from app.sources.public_api.good_price import parse_csv_bytes

    csv_text = "업소명,소재지도로명주소,품목1,가격1,위도,경도\n평택식당,경기도 평택시 1,국밥,\"9,000\",36.99,127.11\n"
    for encoding in ("cp949", "utf-8-sig"):
        rows = parse_csv_bytes(csv_text.encode(encoding))
        assert rows[0]["업소명"] == "평택식당"
        parsed = parse_row(rows[0])
        assert parsed is not None
        assert parsed["menu_items"] == [("국밥", 9000.0)]


def test_parse_csv_bytes_rejects_undecodable():
    import pytest

    from app.sources.public_api.good_price import parse_csv_bytes

    with pytest.raises(ValueError):
        parse_csv_bytes(b"\xff\xfe\x00\x01\x02\x81")
