import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from app.domain.enums import Category
from app.ingestion.normalize import normalize
from app.sources.public_api.adapters import SportsFacilityAdapter, _map_sports_item

# 사용자가 제공한 실제 응답 예시 그대로 (XML 태그 -> dict)
SAMPLE_ITEM = {
    "addr_ctpv_nm": "서울특별시",
    "nation_yn": "N",
    "row_num": "1",
    "base_ymd": "20210504",
    "faci_stat_nm": "정상운영",
    "reg_dt": "2021-12-30",
    "inout_gbn_nm": "없음",
    "faci_lat": "37.5578385325826",
    "faci_cd": "1F63F23E59FAAC4FBB252717CCC23022",
    "faci_zip": "04527",
    "faci_gfa": "0",
    "ftype_nm": "체력단련장",
    "cpb_nm": "중구",
    "addr_emd_nm": "남대문로5가",
    "addr_cpb_nm": "중구",
    "faci_road_zip": "04527",
    "faci_tel_no": "02-6411-6154",
    "faci_lot": "126.9744151",
    "updt_dt": "2026-06-30",
    "faci_gb_nm": "신고",
    "cp_nm": "서울특별시",
    "faci_nm": "그랜드센트럴 피트니스",
    "faci_road_addr": "서울특별시 중구 세종대로 14(남대문로5가)",
    "atnm_chk_yn": "Y",
    "fcob_nm": "체력단련장업",
    "faci_addr": "서울특별시 중구 남대문로5가 831 그랜드센트럴(GRAND CENTRAL)",
}

SAMPLE_XML = """<response>
<script src="chrome-extension://necpbmbhhdiplmfhmjicabdeighkndkn/frame_ant/frame_ant.js"/>
<header>
<resultCode>00</resultCode>
<resultMsg>NORMAL SERVICE</resultMsg>
</header>
<body>
<pageNo>1</pageNo>
<totalCount>1</totalCount>
<numOfRows>10</numOfRows>
<items>
<item>
<faci_nm>그랜드센트럴 피트니스</faci_nm>
<faci_stat_nm>정상운영</faci_stat_nm>
<faci_lat>37.5578385325826</faci_lat>
<faci_lot>126.9744151</faci_lot>
<faci_road_addr>서울특별시 중구 세종대로 14(남대문로5가)</faci_road_addr>
<faci_addr>서울특별시 중구 남대문로5가 831 그랜드센트럴(GRAND CENTRAL)</faci_addr>
<ftype_nm>체력단련장</ftype_nm>
<fcob_nm>체력단련장업</fcob_nm>
<faci_tel_no>02-6411-6154</faci_tel_no>
<faci_cd>1F63F23E59FAAC4FBB252717CCC23022</faci_cd>
<cp_nm>서울특별시</cp_nm>
<addr_cpb_nm>중구</addr_cpb_nm>
</item>
<item>
<faci_nm>폐업한 체육관</faci_nm>
<faci_stat_nm>폐업</faci_stat_nm>
<faci_lat>37.1</faci_lat>
<faci_lot>127.1</faci_lot>
</item>
</items>
</body>
</response>"""


def test_map_sports_item_extracts_fields():
    mapped = _map_sports_item(SAMPLE_ITEM)
    assert mapped is not None
    assert mapped["place_name"] == "그랜드센트럴 피트니스"
    assert mapped["lat"] == 37.5578385325826
    assert mapped["lng"] == 126.9744151
    assert mapped["address"] == "서울특별시 중구 세종대로 14(남대문로5가)"
    assert mapped["extra"]["facility_type"] == "체력단련장"


def test_map_sports_item_excludes_closed_facilities():
    item = dict(SAMPLE_ITEM)
    item["faci_stat_nm"] = "폐업"
    assert _map_sports_item(item) is None


def test_mapped_item_normalizes_to_local_benefit_not_discount():
    mapped = _map_sports_item(SAMPLE_ITEM)
    offer = normalize(mapped, SportsFacilityAdapter.source, SportsFacilityAdapter.layer)
    assert offer.category == Category.LOCAL_BENEFIT


def test_fetch_raw_parses_real_xml_sample_and_skips_closed():
    request = httpx.Request("GET", "https://apis.data.go.kr/B551014/SRVC_API_SFMS_FACI")
    response = httpx.Response(200, request=request, text=SAMPLE_XML)
    adapter = SportsFacilityAdapter()
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        result = asyncio.run(adapter.fetch_raw())
    assert len(result) == 1
    assert result[0]["place_name"] == "그랜드센트럴 피트니스"
