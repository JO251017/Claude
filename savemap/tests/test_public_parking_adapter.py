import asyncio
from unittest.mock import AsyncMock, patch

from app.domain.enums import Category, SourceType
from app.ingestion.normalize import normalize
from app.sources.public_api.adapters import PublicParkingAdapter, _map_parking_item

SAMPLE_RAW_ITEM = {
    "prkplceNo": "12345",
    "prkplceNm": "평택시청 공영주차장",
    "prkplceSe": "공영",
    "prkplceType": "노외",
    "rdnmadr": "경기도 평택시 중앙로 1",
    "lnmadr": "경기도 평택시 통복동 100",
    "prkcmprt": "80",
    "latitude": "36.9925",
    "longitude": "127.1130",
    "basicTime": "30",
    "basicCharge": "500",
    "addUnitTime": "10",
    "addUnitCharge": "200",
    "dayCmmtkt": "10000",
    "monthCmmtkt": "80000",
    "weekdayOperOpenHhmm": "0900",
    "weekdayOperColseHhmm": "1800",
    "satOperOperOpenHhmm": "",
    "satOperCloseHhmm": "",
    "holidayOperOpenHhmm": "",
    "holidayCloseOpenHhmm": "",
    "institutionNm": "평택시청",
    "phoneNumber": "031-000-0000",
    "pwdbsPpkZoneYn": "Y",
}


def test_map_parking_item_extracts_core_fields():
    mapped = _map_parking_item(SAMPLE_RAW_ITEM)
    assert mapped["place_name"] == "평택시청 공영주차장"
    assert mapped["lat"] == 36.9925
    assert mapped["lng"] == 127.1130
    assert mapped["external_ref"] == "12345"
    assert mapped["address"] == "경기도 평택시 중앙로 1"
    assert mapped["extra"]["basic_charge"] == "500"
    assert mapped["extra"]["disabled_parking_zone"] == "Y"


def test_map_parking_item_falls_back_to_lnmadr_when_no_road_address():
    item = dict(SAMPLE_RAW_ITEM)
    item["rdnmadr"] = ""
    mapped = _map_parking_item(item)
    assert mapped["address"] == "경기도 평택시 통복동 100"


def test_mapped_item_normalizes_to_free_parking_category():
    mapped = _map_parking_item(SAMPLE_RAW_ITEM)
    offer = normalize(mapped, SourceType.S1_PUBLIC, PublicParkingAdapter.layer)
    assert offer.category == Category.FREE_PARKING
    assert offer.place_name == "평택시청 공영주차장"
    assert offer.extra["operating_hours"]["weekday"] == ["0900", "1800"]


def test_map_parking_item_handles_missing_coordinates():
    item = dict(SAMPLE_RAW_ITEM)
    item["latitude"] = ""
    item["longitude"] = None
    mapped = _map_parking_item(item)
    assert mapped["lat"] is None
    assert mapped["lng"] is None


def test_fetch_raw_parses_multi_item_envelope():
    envelope = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
            "body": {
                "items": {"item": [SAMPLE_RAW_ITEM, SAMPLE_RAW_ITEM]},
                "numOfRows": 100,
                "pageNo": 1,
                "totalCount": 2,
            },
        }
    }
    adapter = PublicParkingAdapter()
    with patch(
        "app.sources.public_api.adapters.GovDataClient.fetch",
        new=AsyncMock(return_value=envelope),
    ):
        result = asyncio.run(adapter.fetch_raw())
    assert len(result) == 2
    assert result[0]["place_name"] == "평택시청 공영주차장"


def test_fetch_raw_handles_single_item_dict_envelope():
    envelope = {"response": {"body": {"items": {"item": SAMPLE_RAW_ITEM}}}}
    adapter = PublicParkingAdapter()
    with patch(
        "app.sources.public_api.adapters.GovDataClient.fetch",
        new=AsyncMock(return_value=envelope),
    ):
        result = asyncio.run(adapter.fetch_raw())
    assert len(result) == 1


def test_fetch_raw_handles_nodata_envelope():
    envelope = {"response": {"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"}, "body": {"items": ""}}}
    adapter = PublicParkingAdapter()
    with patch(
        "app.sources.public_api.adapters.GovDataClient.fetch",
        new=AsyncMock(return_value=envelope),
    ):
        result = asyncio.run(adapter.fetch_raw())
    assert result == []
