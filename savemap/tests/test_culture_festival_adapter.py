import asyncio
from unittest.mock import AsyncMock, patch

from app.domain.enums import Category
from app.ingestion.normalize import normalize
from app.sources.public_api.adapters import CultureFestivalAdapter, _map_festival_item

SAMPLE_ITEM = {
    "fstvlId": "F001",
    "fstvlNm": "평택 물빛축제",
    "rdnmadr": "경기도 평택시 중앙로 1",
    "lnmadr": "경기도 평택시 통복동 1",
    "latitude": "36.9925",
    "longitude": "127.1130",
    "fstvlStartDate": "20260801",
    "fstvlEndDate": "20260803",
    "auspcInsttNm": "평택시",
    "phoneNumber": "031-000-0000",
}


def test_map_festival_item_extracts_core_fields():
    mapped = _map_festival_item(SAMPLE_ITEM)
    assert mapped is not None
    assert mapped["place_name"] == "평택 물빛축제"
    assert mapped["lat"] == 36.9925
    assert mapped["lng"] == 127.1130
    assert mapped["expires_at"].strftime("%Y%m%d") == "20260803"
    assert mapped["valid_from"].strftime("%Y%m%d") == "20260801"


def test_map_festival_item_skips_when_end_date_missing():
    item = dict(SAMPLE_ITEM)
    del item["fstvlEndDate"]
    assert _map_festival_item(item) is None


def test_map_festival_item_skips_when_name_missing():
    item = dict(SAMPLE_ITEM)
    del item["fstvlNm"]
    assert _map_festival_item(item) is None


def test_mapped_item_normalizes_to_local_benefit_category_and_requires_expiry():
    mapped = _map_festival_item(SAMPLE_ITEM)
    offer = normalize(mapped, CultureFestivalAdapter.source, CultureFestivalAdapter.layer)
    assert offer.category == Category.LOCAL_BENEFIT
    assert offer.expires_at is not None


def test_fetch_raw_skips_unparseable_items_without_crashing():
    envelope = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        SAMPLE_ITEM,
                        {"fstvlNm": "필드 부족 축제"},  # 좌표/종료일 없음 -> 건너뜀
                    ]
                }
            }
        }
    }
    adapter = CultureFestivalAdapter()
    with patch(
        "app.sources.public_api.adapters.GovDataClient.fetch",
        new=AsyncMock(return_value=envelope),
    ):
        result = asyncio.run(adapter.fetch_raw())
    assert len(result) == 1
    assert result[0]["place_name"] == "평택 물빛축제"
