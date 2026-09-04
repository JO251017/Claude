import asyncio

from app.sources.public_api.dine_out_price import (
    _extract_rows,
    normalize_region,
    parse_csv_bytes,
    parse_price,
    parse_row,
    region_from_address,
    store_rows,
    sync_dine_out_prices,
)


def test_region_aliases_collapse_to_short_form():
    assert normalize_region("충청남도") == "충남"
    assert normalize_region("충남") == "충남"
    assert normalize_region("경기도") == "경기"
    assert normalize_region("서울특별시") == "서울"
    assert normalize_region(" 강원특별자치도 ") == "강원"


def test_region_normalization_rejects_non_sido():
    # 시군구를 시도로 오인하면 엉뚱한 지역 평균과 비교하게 된다.
    assert normalize_region("아산시") is None
    assert normalize_region("") is None
    assert normalize_region(None) is None


def test_region_from_address_reads_the_leading_sido():
    assert region_from_address("충청남도 아산시 배방읍 모산로 151-2") == "충남"
    assert region_from_address("경기도 평택시 중앙로 1") == "경기"
    # 시도로 시작하지 않으면 비교를 건너뛴다.
    assert region_from_address("아산시 배방읍 모산로 151-2") is None
    assert region_from_address(None) is None


def test_parse_price_handles_formats_and_rejects_impossible_values():
    assert parse_price("12,538") == 12538.0
    assert parse_price("12538원") == 12538.0
    assert parse_price(12538.0) == 12538.0
    # 단위가 다른 컬럼을 잘못 읽었을 때 이상한 기준가가 조용히 들어가면 안 된다.
    assert parse_price("12") is None
    assert parse_price("9999999") is None
    assert parse_price("") is None


def test_parse_row_maps_dish_and_region():
    row = {"품목명": "칼국수", "지역명": "충청남도", "평균가격": "9,200", "조사년월": "2026-07"}
    assert parse_row(row) == {
        "dish": "칼국수",
        "region": "충남",
        "price": 9200.0,
        "survey_period": "2026-07",
    }


def test_parse_row_accepts_alternate_column_names():
    # 배포본마다 컬럼명이 갈려서 후보를 여러 개 인식해야 한다.
    row = {"itemName": "냉면", "sidoName": "경기", "avgPrice": 11000}
    parsed = parse_row(row)
    assert parsed is not None
    assert parsed["dish"] == "냉면" and parsed["region"] == "경기"


def test_parse_row_skips_items_outside_the_survey():
    # 참가격 외식비에 없는 품목까지 억지로 넣으면 기준이 없는데 있는 것처럼 보인다.
    assert parse_row({"품목명": "아메리카노", "지역명": "경기", "평균가격": "4500"}) is None
    assert parse_row({"품목명": "칼국수", "지역명": "아산시", "평균가격": "9200"}) is None
    assert parse_row({"품목명": "칼국수", "지역명": "경기"}) is None


def test_extract_rows_handles_both_response_shapes():
    assert _extract_rows({"data": [{"a": 1}]}) == [{"a": 1}]
    assert _extract_rows(
        {"response": {"body": {"items": {"item": [{"b": 2}]}}}}
    ) == [{"b": 2}]
    # item이 하나면 dict로 오는 배포본도 있다.
    assert _extract_rows({"response": {"body": {"items": {"item": {"c": 3}}}}}) == [{"c": 3}]
    assert _extract_rows({"unexpected": 1}) == []


def test_parse_csv_bytes_reads_cp949():
    csv_text = "품목명,지역명,평균가격\n김밥,충청남도,3200\n"
    rows = parse_csv_bytes(csv_text.encode("cp949"))
    assert rows[0]["품목명"] == "김밥"


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """RegionalPriceStat upsert만 확인하면 되므로 최소한만 흉내낸다."""

    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.committed = False

    async def execute(self, _stmt):
        return _FakeResult(self.existing)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def test_store_rows_creates_new_stats():
    session = _FakeSession()
    result = asyncio.run(
        store_rows(session, [{"품목명": "칼국수", "지역명": "충청남도", "평균가격": "9200"}])
    )
    assert result["created"] == 1 and result["updated"] == 0
    assert session.added[0].dish == "칼국수" and session.added[0].region == "충남"
    assert session.committed


def test_store_rows_updates_existing_stat():
    class _Existing:
        price = 8000.0
        survey_period = "2026-06"

    existing = _Existing()
    session = _FakeSession(existing=existing)
    result = asyncio.run(
        store_rows(
            session,
            [{"품목명": "칼국수", "지역명": "충남", "평균가격": "9200", "조사년월": "2026-07"}],
        )
    )
    assert result["updated"] == 1 and result["created"] == 0
    assert existing.price == 9200.0 and existing.survey_period == "2026-07"


def test_store_rows_exposes_raw_keys_when_nothing_parses():
    # 필드명 추측이 틀렸을 때 "0건"만 보이면 무엇을 고쳐야 할지 알 수 없다.
    session = _FakeSession()
    result = asyncio.run(store_rows(session, [{"엉뚱한컬럼": "값", "다른컬럼": 1}]))
    assert result["usable_rows"] == 0
    assert result["sample_raw_keys"] == ["다른컬럼", "엉뚱한컬럼"]


def test_sync_skips_when_url_not_configured(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "dine_out_price_api_url", "")
    result = asyncio.run(sync_dine_out_prices(_FakeSession()))
    assert result["skipped"] is True
