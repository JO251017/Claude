from app.sources.public_api.restaurant_registry import parse_row


def test_parse_row_with_priority_field_codes_from_application_screen():
    # 활용신청 화면에서 실제 확인된 조건 필드코드(BPLC_NM 등)가 응답 항목명으로도
    # 그대로 오는 경우를 최우선으로 인식하는지 확인 — 한글 컬럼명과 안 섞여도 동작해야 함.
    row = {
        "BPLC_NM": "평택식당",
        "ROAD_NM_ADDR": "경기도 평택시 중앙로 1",
        "SALS_STTS_NM": "영업/정상",
        "UPTAE_NM": "한식",
    }
    parsed = parse_row(row, "일반음식점")
    assert parsed is not None
    assert parsed["name"] == "평택식당"
    assert parsed["address"] == "경기도 평택시 중앙로 1"
    assert parsed["category"] == "일반음식점 > 한식"


def test_parse_row_with_localdata_standard_columns():
    row = {
        "사업장명": "평택식당",
        "도로명전체주소": "경기도 평택시 중앙로 1",
        "소재지전화": "031-000-0000",
        "업태구분명": "한식",
        "영업상태명": "영업/정상",
    }
    parsed = parse_row(row, "일반음식점")
    assert parsed is not None
    assert parsed["name"] == "평택식당"
    assert parsed["address"] == "경기도 평택시 중앙로 1"
    assert parsed["phone"] == "031-000-0000"
    assert parsed["category"] == "일반음식점 > 한식"
    assert parsed["lat"] is None and parsed["lng"] is None


def test_parse_row_rejects_closed_business():
    row = {
        "사업장명": "폐업한가게",
        "도로명전체주소": "경기도 평택시 1",
        "영업상태명": "폐업",
    }
    assert parse_row(row, "일반음식점") is None


def test_parse_row_rejects_missing_name_or_address():
    assert parse_row({"도로명전체주소": "경기도 평택시 1"}, "일반음식점") is None
    assert parse_row({"사업장명": "가게"}, "일반음식점") is None


def test_parse_row_falls_back_to_category_label_without_business_type():
    row = {"사업장명": "가게", "도로명전체주소": "경기도 평택시 1"}
    parsed = parse_row(row, "휴게음식점")
    assert parsed["category"] == "휴게음식점"


def test_parse_row_uses_coords_when_present_and_in_korea():
    row = {
        "사업장명": "가게",
        "도로명전체주소": "경기도 평택시 1",
        "위도": "36.99",
        "경도": "127.11",
    }
    parsed = parse_row(row, "일반음식점")
    assert abs(parsed["lat"] - 36.99) < 1e-6


def test_parse_row_discards_out_of_korea_coords():
    row = {
        "사업장명": "가게",
        "도로명전체주소": "경기도 평택시 1",
        "위도": "3.69",
        "경도": "12.71",
    }
    parsed = parse_row(row, "일반음식점")
    assert parsed is not None
    assert parsed["lat"] is None


def test_store_rows_creates_places_without_menu_items():
    import asyncio

    from app.sources.public_api import restaurant_registry

    class _FakeResult:
        def scalars(self):
            return self

        def first(self):
            return None

    class _FakeSession:
        def __init__(self):
            self.added = []
            self.committed = 0

        async def execute(self, *a, **kw):
            return _FakeResult()

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            pass

        async def commit(self):
            self.committed += 1

        async def rollback(self):
            pass

    raw_rows = [
        {
            "사업장명": f"가게{i}",
            "도로명전체주소": "경기도 평택시",
            "위도": "36.99",
            "경도": "127.11",
        }
        for i in range(5)
    ]

    session = _FakeSession()
    result = asyncio.run(restaurant_registry.store_rows(session, raw_rows, category_label="일반음식점"))
    assert result["places_created"] == 5
    assert result["parsed_rows"] == 5
    assert len(session.added) == 5
    assert session.committed == 1


def test_store_rows_skips_existing_place_by_name_and_address():
    import asyncio

    from app.sources.public_api import restaurant_registry

    class _FakeResultExisting:
        def scalars(self):
            return self

        def first(self):
            return object()  # 이미 존재하는 Place 취급

    class _FakeSession:
        async def execute(self, *a, **kw):
            return _FakeResultExisting()

        def add(self, obj):
            raise AssertionError("이미 있는 Place를 다시 add하면 안 된다")

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            pass

    raw_rows = [
        {"사업장명": "가게", "도로명전체주소": "경기도 평택시", "위도": "36.99", "경도": "127.11"}
    ]
    result = asyncio.run(
        restaurant_registry.store_rows(_FakeSession(), raw_rows, category_label="일반음식점")
    )
    assert result["places_created"] == 0
    assert result["places_skipped_existing"] == 1


def test_sync_restaurant_registry_requires_region():
    import asyncio

    from app.sources.public_api import restaurant_registry

    result = asyncio.run(
        restaurant_registry.sync_restaurant_registry(None, category="일반음식점", region="")
    )
    assert "skipped" in result


def test_sync_restaurant_registry_rejects_unknown_category():
    import asyncio

    from app.sources.public_api import restaurant_registry

    result = asyncio.run(
        restaurant_registry.sync_restaurant_registry(None, category="편의점", region="평택시")
    )
    assert "skipped" in result


def _fake_response(json_body: dict):
    import httpx

    request = httpx.Request("GET", "https://apis.data.go.kr/1741000/general_restaurants/info")
    return httpx.Response(200, request=request, json=json_body)


def test_fetch_page_parses_response_body_items_item_as_list():
    # apis.data.go.kr 표준 오픈API 응답 포맷(response.header + response.body.items.item) —
    # 처음에 이걸 놓치고 odcloud식 {"data": [...]}로 읽어서 항상 0건이 나오던 실제 장애가
    # 있었다(2026-08-06, 서울로 바꿔도 동일하게 0건).
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.sources.public_api import restaurant_registry

    body = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "items": {"item": [{"BPLC_NM": "가게1"}, {"BPLC_NM": "가게2"}]},
                "totalCount": 2,
            },
        }
    }
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_fake_response(body))):
        rows, has_more = asyncio.run(
            restaurant_registry._fetch_page("general_restaurants", "평택시", 1, 100)
        )
    assert len(rows) == 2
    assert rows[0]["BPLC_NM"] == "가게1"
    assert has_more is False  # totalCount(2) <= page*per_page(100)


def test_fetch_page_handles_single_item_as_dict_not_list():
    # 결과가 1건이면 item이 list가 아니라 dict 하나로 온다 — 흔한 XML→JSON 변환 함정.
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.sources.public_api import restaurant_registry

    body = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {"items": {"item": {"BPLC_NM": "가게1"}}, "totalCount": 1},
        }
    }
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_fake_response(body))):
        rows, _ = asyncio.run(restaurant_registry._fetch_page("general_restaurants", "평택시", 1, 100))
    assert rows == [{"BPLC_NM": "가게1"}]


def test_fetch_page_handles_zero_results_without_crashing():
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.sources.public_api import restaurant_registry

    body = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {"items": "", "totalCount": 0},
        }
    }
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_fake_response(body))):
        rows, has_more = asyncio.run(
            restaurant_registry._fetch_page("general_restaurants", "존재하지않는지역", 1, 100)
        )
    assert rows == []
    assert has_more is False


def test_fetch_page_raises_with_result_message_on_logical_error():
    # data.go.kr은 HTTP 200이면서도 resultCode로 논리적 오류(키 미등록 등)를 알리는
    # 경우가 있다 — 이걸 놓치면 "성공했는데 이상하게 0건"으로만 보인다.
    import asyncio
    from unittest.mock import AsyncMock, patch

    import pytest

    from app.sources.public_api import restaurant_registry

    body = {
        "response": {
            "header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"},
            "body": {},
        }
    }
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_fake_response(body))):
        with pytest.raises(RuntimeError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
            asyncio.run(restaurant_registry._fetch_page("general_restaurants", "평택시", 1, 100))
