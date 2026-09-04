import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from app.domain.enums import Category
from app.ingestion.normalize import normalize
from app.integrations.kakao import GeocodeResult
from app.sources.public_api.adapters import OnnuriMerchantAdapter, _map_onnuri_row

SAMPLE_ROW = {
    "가맹점명": "평택전통시장 방앗간",
    "소속 시장명(또는 상점가)": "평택 통복시장",
    "소재지": "경기도 평택시 통복시장로 8",
    "취급품목": "떡, 참기름",
    "지류형 가맹 여부": "Y",
    "디지털형 가맹 여부": "N",
    "등록년도": 2023,
}


def test_map_onnuri_row_extracts_fields_without_coords():
    mapped = _map_onnuri_row(SAMPLE_ROW)
    assert mapped is not None
    assert mapped["place_name"] == "평택전통시장 방앗간"
    assert "lat" not in mapped
    assert mapped["address"] == "경기도 평택시 통복시장로 8"
    assert mapped["extra"]["paper_voucher"] == "Y"


def test_map_onnuri_row_skips_when_name_or_address_missing():
    assert _map_onnuri_row({"소재지": "어딘가"}) is None
    assert _map_onnuri_row({"가맹점명": "이름만"}) is None


def test_mapped_row_normalizes_to_local_benefit_core_base():
    mapped = dict(_map_onnuri_row(SAMPLE_ROW), lat=36.99, lng=127.11)
    offer = normalize(mapped, OnnuriMerchantAdapter.source, OnnuriMerchantAdapter.layer)
    assert offer.category == Category.LOCAL_BENEFIT
    assert offer.expires_at is None


def test_fetch_raw_geocodes_and_skips_ungeocodable_items():
    envelope = {
        "page": 1,
        "perPage": 50,
        "data": [
            SAMPLE_ROW,
            {"가맹점명": "지오코딩 실패 매장", "소재지": "알 수 없는 주소"},
        ],
    }

    async def fake_geocode(query):
        if "알 수 없는" in query:
            return None
        return GeocodeResult(lat=36.9955, lng=127.1071, address=query)

    kakao = AsyncMock()
    kakao.geocode = AsyncMock(side_effect=fake_geocode)
    adapter = OnnuriMerchantAdapter(kakao=kakao, max_items=50)

    request = httpx.Request("GET", "https://api.odcloud.kr/api/3060079/v1/uddi:fake")
    response = httpx.Response(200, request=request, json=envelope)
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        result = asyncio.run(adapter.fetch_raw())

    assert len(result) == 1
    assert result[0]["place_name"] == "평택전통시장 방앗간"
    assert result[0]["lat"] == 36.9955
