import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from app.integrations import kosis


def test_get_latest_cpi_skips_when_no_url(monkeypatch):
    monkeypatch.setattr(kosis.settings, "kosis_cpi_api_url", "")
    result = asyncio.run(kosis.get_latest_cpi())
    assert result is None


def test_parse_rows_computes_yoy_when_year_ago_present():
    rows = [
        {"PRD_DE": "202507", "DT": "110.0"},
        {"PRD_DE": "202607", "DT": "115.5"},
    ]
    snap = kosis._parse_rows(rows)
    assert snap is not None
    assert snap.period == "202607"
    assert snap.index == 115.5
    assert round(snap.yoy_pct, 2) == round((115.5 - 110.0) / 110.0 * 100, 2)


def test_parse_rows_no_year_ago_leaves_yoy_none():
    rows = [{"PRD_DE": "202607", "DT": "115.5"}]
    snap = kosis._parse_rows(rows)
    assert snap is not None
    assert snap.yoy_pct is None


def test_parse_rows_skips_malformed_entries():
    rows = [
        {"PRD_DE": "202606", "DT": "abc"},  # 숫자 아님 → 버림
        {"PRD_DE": "", "DT": "100.0"},  # 기간 없음 → 버림
        {"PRD_DE": "202607", "DT": "115.5"},
    ]
    snap = kosis._parse_rows(rows)
    assert snap is not None
    assert snap.period == "202607"


def test_parse_rows_empty_returns_none():
    assert kosis._parse_rows([]) is None


def _fake_response(rows) -> httpx.Response:
    request = httpx.Request("GET", "https://kosis.kr/openapi/statisticsData.do")
    return httpx.Response(200, request=request, json=rows)


def test_get_latest_cpi_fetches_and_caches(monkeypatch):
    kosis._cache = None
    monkeypatch.setattr(kosis.settings, "kosis_cpi_api_url", "https://kosis.kr/fake")
    rows = [{"PRD_DE": "202507", "DT": "110.0"}, {"PRD_DE": "202607", "DT": "115.5"}]
    mock_get = AsyncMock(return_value=_fake_response(rows))

    with patch("httpx.AsyncClient.get", new=mock_get):
        r1 = asyncio.run(kosis.get_latest_cpi())
        r2 = asyncio.run(kosis.get_latest_cpi())

    assert r1 is not None
    assert r1.index == 115.5
    assert r2 is r1
    assert mock_get.call_count == 1  # 두 번째는 캐시 히트


def test_get_latest_cpi_returns_none_on_error_response_shape(monkeypatch):
    kosis._cache = None
    monkeypatch.setattr(kosis.settings, "kosis_cpi_api_url", "https://kosis.kr/fake")
    request = httpx.Request("GET", "https://kosis.kr/openapi/statisticsData.do")
    error_response = httpx.Response(200, request=request, json={"err": "30", "errMsg": "인증오류"})

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=error_response)):
        result = asyncio.run(kosis.get_latest_cpi())
    assert result is None


def test_get_latest_cpi_returns_none_on_fetch_exception(monkeypatch):
    kosis._cache = None
    monkeypatch.setattr(kosis.settings, "kosis_cpi_api_url", "https://kosis.kr/fake")

    async def raise_error(*args, **kwargs):
        raise httpx.ConnectError("boom")

    with patch("httpx.AsyncClient.get", new=raise_error):
        result = asyncio.run(kosis.get_latest_cpi())
    assert result is None
