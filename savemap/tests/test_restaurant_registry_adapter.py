from app.sources.public_api.restaurant_registry import parse_row


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
