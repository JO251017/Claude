import asyncio
from datetime import datetime

from app.domain.place import Place
from app.sources.public_api.local_currency import (
    apply_local_currency_rows,
    parse_csv_bytes,
    parse_row,
)


def test_parse_row_reads_alternate_column_names():
    assert parse_row(
        {"가맹점명": "행복분식", "소재지도로명주소": "충청남도 아산시 온천대로 1"}
    ) == {"name": "행복분식", "address": "충청남도 아산시 온천대로 1", "category": None}
    assert parse_row({"상호명": "모아카페", "지번주소": "경기도 평택시 1"}) == {
        "name": "모아카페",
        "address": "경기도 평택시 1",
        "category": None,
    }


def test_parse_row_requires_a_name():
    # 상호명이 없는 줄은 지어내지 않고 버린다.
    assert parse_row({"소재지도로명주소": "충청남도 아산시 1"}) is None
    assert parse_row({}) is None


def test_parse_csv_bytes_reads_excel_utf8_bom():
    csv_text = "가맹점명,소재지도로명주소\n행복분식,충남 아산시 1\n"
    rows = parse_csv_bytes(csv_text.encode("utf-8-sig"))
    assert rows[0]["가맹점명"] == "행복분식"


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _FakeSession:
    """apply_local_currency_rows는 select(Place)...offset...limit 한 번만 던지고
    끝난다 — offer_resync 테스트와 같은 성격의 페이크(오프셋/리밋 적용은 실제로는
    DB가 하므로, 여기서는 "이미 그 페이지만큼만 온 결과"를 그대로 돌려준다)."""

    def __init__(self, places):
        self._places = places
        self.commits = 0

    async def execute(self, _stmt):
        return _Result(self._places)

    async def commit(self):
        self.commits += 1


def test_matches_existing_place_by_normalized_name_and_address_prefix():
    place = Place(id=1, name="행복분식", address="충청남도 아산시 온천대로 1")
    session = _FakeSession([place])
    raw_rows = [{"가맹점명": "행복분식", "소재지도로명주소": "충청남도 아산시 배방읍 12"}]

    result = asyncio.run(apply_local_currency_rows(session, raw_rows, limit=500))

    assert result["matched_places"] == 1
    assert result["unmatched"] == 0
    assert place.accepts_local_currency is True
    assert isinstance(place.local_currency_verified_at, datetime)
    assert session.commits == 1


def test_same_name_different_branch_is_left_unmatched():
    # 같은 상호명이 여러 지점일 수 있다 — 주소 앞부분(시도+시군구)이 다르면
    # 잘못된 매장에 배지를 붙이느니 안 붙인다.
    place = Place(id=1, name="행복분식", address="충청남도 아산시 온천대로 1")
    session = _FakeSession([place])
    raw_rows = [{"가맹점명": "행복분식", "소재지도로명주소": "경기도 평택시 12"}]

    result = asyncio.run(apply_local_currency_rows(session, raw_rows, limit=500))

    assert result["matched_places"] == 0
    assert result["unmatched"] == 1
    assert not place.accepts_local_currency
    assert place.local_currency_verified_at is None


def test_no_matching_name_leaves_place_untouched():
    place = Place(id=1, name="다른가게", address="충청남도 아산시 1")
    session = _FakeSession([place])
    raw_rows = [{"가맹점명": "행복분식", "소재지도로명주소": "충청남도 아산시 1"}]

    result = asyncio.run(apply_local_currency_rows(session, raw_rows, limit=500))

    assert result["matched_places"] == 0
    assert result["unmatched"] == 0
    assert not place.accepts_local_currency


def test_zero_usable_rows_exposes_sample_raw_keys():
    session = _FakeSession([])
    result = asyncio.run(apply_local_currency_rows(session, [{"이상한컬럼": "x"}]))

    assert result["usable_rows"] == 0
    assert result["sample_raw_keys"] == ["이상한컬럼"]
    assert result["done"] is True


def test_offset_limit_next_offset_and_done_contract():
    places = [Place(id=i, name="다른가게", address="충남") for i in range(1, 4)]
    session = _FakeSession(places)
    raw_rows = [{"가맹점명": "행복분식", "소재지도로명주소": "충남"}]

    not_done = asyncio.run(apply_local_currency_rows(session, raw_rows, offset=10, limit=3))
    assert not_done["offset"] == 10
    assert not_done["next_offset"] == 13
    assert not_done["done"] is False  # scanned_places(3) == limit(3)

    done = asyncio.run(apply_local_currency_rows(session, raw_rows, offset=10, limit=4))
    assert done["next_offset"] == 13
    assert done["done"] is True  # scanned_places(3) < limit(4)
