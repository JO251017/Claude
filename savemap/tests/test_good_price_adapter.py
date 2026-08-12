from pathlib import Path

from app.sources.public_api.good_price import parse_price, parse_row


def test_parse_price_handles_real_world_formats():
    assert parse_price("9,000") == 9000.0
    assert parse_price("9000원") == 9000.0
    assert parse_price(" 12,500원~ ") == 12500.0
    assert parse_price("") is None
    assert parse_price(None) is None
    assert parse_price("가격문의") is None
    assert parse_price("50") is None  # 비현실적으로 낮은 값은 버림


def test_parse_price_handles_native_numbers_without_inflating_them():
    # xlrd는 엑셀 숫자 셀을 float로 준다 (예: 8800.0). str(8800.0) = "8800.0"이라
    # 숫자만 뽑으면 소수점 뒤 0까지 자릿수로 붙어 88000이 되는 실제 발생한 버그였다.
    assert parse_price(8800.0) == 8800.0
    assert parse_price(2000.0) == 2000.0
    assert parse_price(12000) == 12000.0


def test_parse_row_full_with_numbered_columns():
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


def test_parse_row_rejects_salon_categories():
    # 미용실/이용업(이발소) 비활성화(사용자 지시, 2026-08-12) — 저장 전(파싱 단계)에서
    # 걸러 지오코딩·AI 통상가 추정 비용을 아예 안 들인다.
    salon = parse_row(
        {"업소명": "동네미용실", "업종명": "미용업", "주요품목": "커트", "가격": "8000",
         "위도": "36.99", "경도": "127.11"}
    )
    assert salon is None

    barber = parse_row(
        {"업소명": "이발소", "업종명": "이용업", "주요품목": "이용료", "가격": "7000",
         "위도": "36.99", "경도": "127.11"}
    )
    assert barber is None

    # 식당은 그대로 통과해야 한다 (과도하게 걸러지지 않는지 확인).
    restaurant = parse_row(
        {"업소명": "국밥집", "업종명": "한식", "주요품목": "국밥", "가격": "8000",
         "위도": "36.99", "경도": "127.11"}
    )
    assert restaurant is not None


def test_parse_row_matches_real_goodprice_go_kr_columns():
    # goodprice.go.kr에서 실제로 받은 다운로드 파일의 컬럼 그대로 (2026-07-31 확인).
    # 품목/가격이 번호 없이 단일 쌍이고, 좌표는 아예 없다.
    row = {
        "번호": "1",
        "업종명": "한식",
        "업소명": "88냉삼 본점",
        "주요품목": "냉삼",
        "가격": 8800.0,
        "업소 전화번호": "031-664-9293",
        "주소": "경기도 평택시 고덕국제7로 117 (고덕동) 110호 88냉삼 본점",
    }
    parsed = parse_row(row)
    assert parsed is not None
    assert parsed["name"] == "88냉삼 본점"
    assert parsed["category"] == "한식"
    assert parsed["phone"] == "031-664-9293"
    assert parsed["menu_items"] == [("냉삼", 8800.0)]
    assert parsed["lat"] is None and parsed["lng"] is None  # 지오코딩은 store_rows에서


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


def test_parse_row_missing_coords_parses_but_leaves_lat_lng_none():
    # 좌표가 없어도 버리지 않는다 — store_rows가 나중에 지오코딩으로 채운다.
    parsed = parse_row({"업소명": "가게", "품목1": "국밥", "가격1": "9000"})
    assert parsed is not None
    assert parsed["lat"] is None and parsed["lng"] is None


def test_parse_row_rejects_incomplete_rows():
    # 메뉴 가격 없음 (실제 데이터에서 서비스업 상당수가 '주요품목: -', '가격: '로 온다)
    assert parse_row({"업소명": "가게", "위도": "36.9", "경도": "127.1", "품목1": "국밥"}) is None
    assert parse_row({"업소명": "가게", "주요품목": "-", "가격": ""}) is None
    # 업소명 없음
    assert parse_row({"품목1": "국밥", "가격1": "9000"}) is None
    # 한국 밖 좌표(데이터 오류)는 좌표만 버리고 나머지는 살린다
    parsed = parse_row(
        {"업소명": "가게", "위도": "3.69", "경도": "12.71", "품목1": "국밥", "가격1": "9000"}
    )
    assert parsed is not None
    assert parsed["lat"] is None


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


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_xls_bytes_reads_real_goodprice_export():
    # 고정 픽스처는 실제 goodprice.go.kr 다운로드 파일(2026-07-31 확인)의 헤더/값
    # 구조를 그대로 재현한 것 — 제목행 + 빈행 + 헤더행 + 데이터행.
    from app.sources.public_api.good_price import parse_xls_bytes

    content = (FIXTURES_DIR / "goodprice_sample.xls").read_bytes()
    rows = parse_xls_bytes(content)
    assert len(rows) == 1
    assert rows[0]["업소명"] == "88냉삼 본점"
    parsed = parse_row(rows[0])
    assert parsed is not None
    assert parsed["menu_items"] == [("냉삼", 8800.0)]


def test_parse_xls_bytes_rejects_files_without_header():
    import pytest

    from app.sources.public_api.good_price import parse_xls_bytes

    content = (FIXTURES_DIR / "goodprice_no_header.xls").read_bytes()
    with pytest.raises(ValueError):
        parse_xls_bytes(content)


def test_geocode_missing_coords_fills_from_kakao_and_leaves_failures_none(monkeypatch):
    import asyncio
    from unittest.mock import patch

    from app.integrations.kakao import GeocodeResult
    from app.sources.public_api import good_price

    monkeypatch.setattr(good_price.settings, "kakao_rest_api_key", "fake-key")

    rows = [
        {"name": "찾아지는 가게", "address": "경기도 평택시 1", "lat": None, "lng": None},
        {"name": "안 찾아지는 가게", "address": "존재하지않는주소", "lat": None, "lng": None},
        {"name": "이미 좌표 있음", "address": "서울", "lat": 37.5, "lng": 127.0},
    ]

    async def fake_geocode(self, query):
        if query == "경기도 평택시 1":
            return GeocodeResult(lat=36.99, lng=127.11, address=query)
        return None

    with patch("app.integrations.kakao.KakaoClient.geocode", new=fake_geocode):
        asyncio.run(good_price._geocode_missing_coords(rows))

    assert rows[0]["lat"] == 36.99 and rows[0]["lng"] == 127.11
    assert rows[1]["lat"] is None  # 못 찾으면 지어내지 않고 None 그대로
    assert rows[2]["lat"] == 37.5  # 이미 있던 좌표는 건드리지 않음


def test_geocode_missing_coords_skips_when_no_kakao_key(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.sources.public_api import good_price

    monkeypatch.setattr(good_price.settings, "kakao_rest_api_key", "")
    rows = [{"name": "가게", "address": "경기도 평택시 1", "lat": None, "lng": None}]

    with patch("app.integrations.kakao.KakaoClient.geocode", new=AsyncMock()) as mocked:
        asyncio.run(good_price._geocode_missing_coords(rows))
        mocked.assert_not_called()
    assert rows[0]["lat"] is None


def test_store_rows_paginates_large_regions_without_processing_everything_at_once():
    """서울(수천 건)처럼 큰 지역을 offset/limit으로 쪼개 호출했을 때, 각 페이지가
    딱 그만큼만 처리하고 next_offset/done을 정확히 계산하는지 — 실제 DB 세션 없이
    session.execute/add/flush/commit/rollback 인터페이스만 흉내 낸 페이크로 검증."""
    import asyncio

    from app.sources.public_api import good_price

    class _FakeResult:
        def scalars(self):
            return self

        def first(self):
            return None  # 매번 "새 매장/메뉴" 취급

    class _FakeSession:
        def __init__(self):
            self.committed = 0

        async def execute(self, *a, **kw):
            return _FakeResult()

        def add(self, obj):
            pass

        async def flush(self):
            pass

        async def refresh(self, obj):
            pass

        async def commit(self):
            self.committed += 1

        async def rollback(self):
            pass

    raw_rows = [
        {"업소명": f"평택가게{i}", "주소": "경기도 평택시", "주요품목": "메뉴", "가격": 8000.0, "위도": "36.99", "경도": "127.11"}
        for i in range(25)
    ]

    session = _FakeSession()
    page1 = asyncio.run(good_price.store_rows(session, raw_rows, region="평택", offset=0, limit=10))
    assert page1["total_matching_rows"] == 25
    assert page1["usable_rows"] == 10
    assert page1["next_offset"] == 10
    assert page1["done"] is False

    page2 = asyncio.run(good_price.store_rows(session, raw_rows, region="평택", offset=10, limit=10))
    assert page2["next_offset"] == 20
    assert page2["done"] is False

    page3 = asyncio.run(good_price.store_rows(session, raw_rows, region="평택", offset=20, limit=10))
    assert page3["usable_rows"] == 5  # 마지막 페이지는 남은 것만
    assert page3["next_offset"] == 25
    assert page3["done"] is True


def test_import_job_register_and_lookup_roundtrip():
    from app.sources.public_api import good_price

    parsed = [{"name": "가게", "address": "경기도 평택시", "lat": None, "lng": None, "menu_items": []}]
    job_id = good_price.register_import_job(parsed)

    assert good_price.get_import_job(job_id) is parsed
    assert good_price.get_import_job("존재하지않는id") is None


def test_import_job_cache_evicts_oldest_beyond_max(monkeypatch):
    # 대용량 파일을 여러 번 업로드해도(재시작 없이) 무료 플랜 메모리를 무한정 잡아먹지
    # 않도록, 가장 오래된 것부터 정리한다.
    from app.sources.public_api import good_price

    good_price._IMPORT_JOBS.clear()
    ids = []
    for i in range(good_price._IMPORT_JOB_MAX + 2):
        ids.append(good_price.register_import_job([{"seq": i}]))

    assert len(good_price._IMPORT_JOBS) == good_price._IMPORT_JOB_MAX
    assert good_price.get_import_job(ids[0]) is None  # 가장 먼저 등록한 건 정리됨
    assert good_price.get_import_job(ids[-1]) is not None  # 가장 최근 건 남아있음


def test_store_parsed_rows_skips_re_parsing_and_matches_store_rows_shape():
    # store_rows(파일 파싱 포함)와 store_parsed_rows(이미 파싱된 행)가 같은 결과
    # 모양을 내는지 — import_id 경로가 기존 경로와 동일한 응답 계약을 지키는지 확인.
    import asyncio

    from app.sources.public_api import good_price

    class _FakeResult:
        def scalars(self):
            return self

        def first(self):
            return None

    class _FakeSession:
        async def execute(self, *a, **kw):
            return _FakeResult()

        def add(self, obj):
            pass

        async def flush(self):
            pass

        async def refresh(self, obj):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            pass

    parsed = [
        {
            "name": "평택가게",
            "address": "경기도 평택시",
            "phone": None,
            "category": "한식",
            "lat": 36.99,
            "lng": 127.11,
            "menu_items": [("국밥", 8000.0)],
        }
    ]

    result = asyncio.run(good_price.store_parsed_rows(_FakeSession(), parsed, region="평택"))
    assert result["places_created"] == 1
    assert result["menu_items_created"] == 1
    assert result["done"] is True


def test_estimate_typical_prices_skips_when_no_gemini_key(monkeypatch):
    import asyncio

    from app.sources.public_api import good_price

    monkeypatch.setattr(good_price.settings, "gemini_api_key", "")
    result = asyncio.run(good_price._estimate_typical_prices({"냉삼", "커트"}))
    assert result == {}


def test_estimate_typical_prices_calls_gemini_once_per_unique_name(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.sources.public_api import good_price

    good_price._TYPICAL_PRICE_CACHE.clear()
    monkeypatch.setattr(good_price.settings, "gemini_api_key", "fake-key")

    async def fake_estimate(self, name):
        return {"냉삼": 9000.0, "커트": 12000.0}.get(name)

    with patch(
        "app.integrations.gemini.GeminiVisionClient.estimate_typical_price",
        new=fake_estimate,
    ):
        result = asyncio.run(good_price._estimate_typical_prices({"냉삼", "커트"}))

    assert result == {"냉삼": 9000.0, "커트": 12000.0}

    # 같은 이름을 다시 물어보면 캐시에서 바로 나오고 Gemini를 다시 부르지 않는다.
    with patch(
        "app.integrations.gemini.GeminiVisionClient.estimate_typical_price",
        new=AsyncMock(side_effect=AssertionError("캐시가 있으면 다시 호출하면 안 됨")),
    ):
        result2 = asyncio.run(good_price._estimate_typical_prices({"냉삼"}))
    assert result2 == {"냉삼": 9000.0}


def test_estimate_typical_prices_one_failure_does_not_block_others(monkeypatch):
    import asyncio
    from unittest.mock import patch

    from app.sources.public_api import good_price

    good_price._TYPICAL_PRICE_CACHE.clear()
    monkeypatch.setattr(good_price.settings, "gemini_api_key", "fake-key")

    async def flaky_estimate(self, name):
        if name == "실패품목":
            raise RuntimeError("Gemini 요청 실패")
        return 5000.0

    with patch(
        "app.integrations.gemini.GeminiVisionClient.estimate_typical_price",
        new=flaky_estimate,
    ):
        result = asyncio.run(good_price._estimate_typical_prices({"정상품목", "실패품목"}))

    assert result["정상품목"] == 5000.0
    assert result["실패품목"] is None


def test_store_parsed_rows_fills_ai_typical_price_from_batched_estimate(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.sources.public_api import good_price

    class _FakeResult:
        def scalars(self):
            return self

        def first(self):
            return None

    class _FakeSession:
        async def execute(self, *a, **kw):
            return _FakeResult()

        def add(self, obj):
            pass

        async def flush(self):
            pass

        async def refresh(self, obj):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            pass

    monkeypatch.setattr(good_price.settings, "gemini_api_key", "fake-key")
    good_price._TYPICAL_PRICE_CACHE.clear()

    captured_items = []

    async def fake_sync_menu_offer(session, place, item):
        captured_items.append(item)

    parsed = [
        {
            "name": "평택가게", "address": "경기도 평택시", "phone": None, "category": "한식",
            "lat": 36.99, "lng": 127.11, "menu_items": [("냉삼", 8000.0)],
        }
    ]

    with (
        patch(
            "app.sources.public_api.good_price._estimate_typical_prices",
            new=AsyncMock(return_value={"냉삼": 9000.0}),
        ),
        patch("app.sources.public_api.good_price.sync_menu_offer", new=fake_sync_menu_offer),
    ):
        result = asyncio.run(good_price.store_parsed_rows(_FakeSession(), parsed, region="평택"))

    assert result["menu_items_created"] == 1
    assert len(captured_items) == 1
    assert captured_items[0].ai_typical_price == 9000.0


def test_store_parsed_rows_refreshes_newly_created_place_before_syncing_offer():
    # flush 직후의 place.geom은 우리가 assign한 EWKT 문자열 그대로라, 그 상태로
    # sync_menu_offer(to_shape(place.geom) 호출)에 넘기면 geoalchemy2가
    # "Only WKBElement and WKTElement objects are supported"로 실패하고 rollback돼서
    # 아무것도 저장 안 되는 실제 장애가 있었다(2026-08-11, 전국 착한가격업소 임포트
    # 13,103건이 전부 "성공"으로 집계됐지만 실제로는 0건 저장됨). refresh를 빼먹으면
    # 바로 이 회귀를 다시 만드니, refresh가 실제로 호출되는지 직접 확인한다.
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.engine.price_comparison import MenuPriceComparison
    from app.sources.public_api import good_price

    class _FakeResult:
        def scalars(self):
            return self

        def first(self):
            return None  # 항상 "새 Place" 취급

    class _TrackingSession:
        def __init__(self):
            self.refreshed = []

        async def execute(self, *a, **kw):
            return _FakeResult()

        def add(self, obj):
            pass

        async def flush(self):
            pass

        async def refresh(self, obj):
            self.refreshed.append(obj)

        async def commit(self):
            pass

        async def rollback(self):
            pass

    parsed = [
        {
            "name": "평택가게",
            "address": "경기도 평택시",
            "phone": None,
            "category": "한식",
            "lat": 36.99,
            "lng": 127.11,
            "menu_items": [("국밥", 8000.0)],
        }
    ]

    # sync_menu_offer 자체는 (to_shape 등 실제 geoalchemy2 변환이 필요해) 진짜 DB
    # 없이는 흉내내기 어려우니 모킹한다 — 이 테스트가 검증하려는 건 딱 하나,
    # "refresh가 sync_menu_offer보다 먼저 호출되는가"다.
    fake_cmp = MenuPriceComparison(
        menu_item_id=1, name="국밥", store_price=8000.0, place_id=1, region_average=None,
        region_median=None, sample_count=0, savings_amount=None, savings_rate=None,
        reliable=False, benchmark_source=None, benchmark_price=None,
    )
    call_order = []
    session = _TrackingSession()

    async def fake_sync_menu_offer(sess, place, item):
        call_order.append("sync_menu_offer")
        return fake_cmp

    original_refresh = session.refresh

    async def tracking_refresh(obj):
        call_order.append("refresh")
        await original_refresh(obj)

    session.refresh = tracking_refresh

    with patch("app.sources.public_api.good_price.sync_menu_offer", new=AsyncMock(side_effect=fake_sync_menu_offer)):
        result = asyncio.run(good_price.store_parsed_rows(session, parsed, region="평택"))

    assert len(session.refreshed) == 1, "새로 만든 Place는 sync_menu_offer 전에 refresh돼야 한다"
    assert call_order == ["refresh", "sync_menu_offer"], "refresh가 sync_menu_offer보다 먼저 일어나야 한다"
    assert result["places_created"] == 1
    assert result["failed_rows"] == 0


