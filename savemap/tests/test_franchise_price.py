import asyncio

from app.domain.franchise import FranchiseBrand
from app.sources.public_api.franchise_price import (
    brand_keywords,
    import_price_rows,
    matches_brand,
    normalize_store_name,
    parse_csv_bytes,
    parse_price,
    parse_row,
)


def test_store_name_normalization_ignores_spacing_and_punctuation():
    assert normalize_store_name("스타벅스 아산점") == "스타벅스아산점"
    assert normalize_store_name("빽다방(평택역점)") == "빽다방평택역점"
    assert normalize_store_name(None) == ""


def test_brand_matching_finds_the_chain_in_a_branch_name():
    brand = FranchiseBrand(name="스타벅스", match_keywords="스타벅스|starbucks")
    assert matches_brand("스타벅스 아산탕정점", brand)
    assert matches_brand("STARBUCKS 천안신부점", brand)
    assert not matches_brand("스타 커피", brand)


def test_brand_without_keywords_falls_back_to_its_name():
    brand = FranchiseBrand(name="빽다방")
    assert brand_keywords(brand) == ["빽다방"]
    assert matches_brand("빽다방 평택점", brand)


def test_too_short_keywords_are_rejected():
    # 한 글자 키워드는 엉뚱한 가게에 붙는다.
    brand = FranchiseBrand(name="본죽", match_keywords="본|본죽")
    assert brand_keywords(brand) == ["본죽"]
    assert not matches_brand("본가한식", brand)


def test_parse_price_rejects_impossible_values():
    assert parse_price("4,500") == 4500.0
    assert parse_price(4500) == 4500.0
    assert parse_price("45") is None
    assert parse_price("") is None


def test_parse_row_reads_the_documented_columns():
    row = {
        "브랜드": "스타벅스",
        "매칭키워드": "스타벅스|starbucks",
        "메뉴명": "아메리카노",
        "가격": "4,500",
        "출처URL": "https://example.com/price",
        "기준년월": "2026-08",
    }
    assert parse_row(row) == {
        "brand": "스타벅스",
        "keywords": "스타벅스|starbucks",
        "official_url": "https://example.com/price",
        "item_name": "아메리카노",
        "price": 4500.0,
        "period": "2026-08",
    }


def test_parse_row_requires_brand_item_and_price():
    # 가격을 지어내지 않는다 — 셋 중 하나라도 없으면 그 줄은 버린다.
    assert parse_row({"브랜드": "스타벅스", "메뉴명": "아메리카노"}) is None
    assert parse_row({"메뉴명": "아메리카노", "가격": "4500"}) is None
    assert parse_row({"브랜드": "스타벅스", "가격": "4500"}) is None


def test_parse_csv_bytes_reads_excel_utf8_bom():
    csv_text = "브랜드,메뉴명,가격\n빽다방,아메리카노,1500\n"
    rows = parse_csv_bytes(csv_text.encode("utf-8-sig"))
    assert rows[0]["브랜드"] == "빽다방"


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """브랜드 조회는 항상 없음(신규 생성 경로)으로 두고 upsert 흐름만 확인한다."""

    def __init__(self):
        self.added = []
        self.committed = False
        self._next_id = 1

    async def execute(self, _stmt):
        return _FakeResult(None)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self._next_id
            self._next_id += 1
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True


def test_import_creates_brand_and_prices():
    session = _FakeSession()
    result = asyncio.run(
        import_price_rows(
            session,
            [
                {"브랜드": "빽다방", "메뉴명": "아메리카노", "가격": "1500"},
                {"브랜드": "빽다방", "메뉴명": "카페라떼", "가격": "2500"},
            ],
        )
    )
    assert result["usable_rows"] == 2
    assert result["prices_created"] == 2
    assert session.committed


def test_import_exposes_raw_keys_when_nothing_parses():
    session = _FakeSession()
    result = asyncio.run(import_price_rows(session, [{"이상한컬럼": "x"}]))
    assert result["usable_rows"] == 0
    assert result["sample_raw_keys"] == ["이상한컬럼"]
