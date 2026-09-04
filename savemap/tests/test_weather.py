import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx

from app.integrations import weather


def test_latlng_to_grid_matches_kma_reference_seoul_city_hall():
    # 기상청 공식 격자표 기준값(서울특별시청) — 변환식이 맞는지 확인하는 기준점.
    assert weather._latlng_to_grid(37.5665, 126.9780) == (60, 127)


def test_base_datetime_kst_uses_previous_hour_before_minute_40():
    before = datetime(2026, 8, 27, 3, 20, tzinfo=timezone.utc)  # KST 12:20
    assert weather._base_datetime_kst(before) == ("20260827", "1100")

    after = datetime(2026, 8, 27, 3, 45, tzinfo=timezone.utc)  # KST 12:45
    assert weather._base_datetime_kst(after) == ("20260827", "1200")


def test_parse_snapshot_rain_and_hot():
    items = [{"category": "PTY", "obsrValue": "1"}, {"category": "T1H", "obsrValue": "30.5"}]
    snap = weather._parse_snapshot(items, datetime.now(timezone.utc))
    assert snap.condition == "rain"
    assert snap.temp_c == 30.5
    assert snap.is_hot is True
    assert snap.is_cold is False


def test_parse_snapshot_snow_and_cold():
    items = [{"category": "PTY", "obsrValue": "3"}, {"category": "T1H", "obsrValue": "-2"}]
    snap = weather._parse_snapshot(items, datetime.now(timezone.utc))
    assert snap.condition == "snow"
    assert snap.is_cold is True


def test_parse_snapshot_missing_or_malformed_values_defaults_to_clear_with_no_temp():
    items = [{"category": "PTY", "obsrValue": ""}, {"category": "T1H", "obsrValue": "abc"}]
    snap = weather._parse_snapshot(items, datetime.now(timezone.utc))
    assert snap.condition == "clear"
    assert snap.temp_c is None
    assert snap.is_hot is False
    assert snap.is_cold is False


def test_get_current_weather_skips_when_no_key_at_all(monkeypatch):
    monkeypatch.setattr(weather.settings, "weather_api_key", "")
    monkeypatch.setattr(weather.settings, "data_go_kr_key", "")
    result = asyncio.run(weather.get_current_weather(37.5665, 126.9780))
    assert result is None


def _fake_kma_response(pty: str, t1h: str) -> httpx.Response:
    request = httpx.Request("GET", weather.KMA_BASE_URL)
    body = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {"category": "PTY", "obsrValue": pty},
                        {"category": "T1H", "obsrValue": t1h},
                    ]
                }
            }
        }
    }
    return httpx.Response(200, request=request, json=body)


def test_get_current_weather_falls_back_to_shared_data_go_kr_key(monkeypatch):
    """기상청 API도 data.go.kr 소속이라, 착한가격업소/지역화폐 어댑터가 이미
    쓰는 공용 인증키로 조회돼야 한다 — 전용 키(WEATHER_API_KEY)를 새로 안 받아도
    된다는 게 이 폴백의 핵심."""
    weather._weather_cache.clear()
    monkeypatch.setattr(weather.settings, "weather_api_key", "")
    monkeypatch.setattr(weather.settings, "data_go_kr_key", "shared-data-go-kr-key")
    response = _fake_kma_response("0", "18.0")

    captured_params = {}

    async def fake_get(self, url, params=None, **kwargs):
        captured_params.update(params or {})
        return response

    with patch("httpx.AsyncClient.get", new=fake_get):
        result = asyncio.run(weather.get_current_weather(37.5665, 126.9780))

    assert result is not None
    assert result.condition == "clear"
    assert captured_params["serviceKey"] == "shared-data-go-kr-key"


def test_get_current_weather_prefers_dedicated_key_over_shared(monkeypatch):
    weather._weather_cache.clear()
    monkeypatch.setattr(weather.settings, "weather_api_key", "dedicated-key")
    monkeypatch.setattr(weather.settings, "data_go_kr_key", "shared-data-go-kr-key")
    response = _fake_kma_response("0", "18.0")

    captured_params = {}

    async def fake_get(self, url, params=None, **kwargs):
        captured_params.update(params or {})
        return response

    with patch("httpx.AsyncClient.get", new=fake_get):
        asyncio.run(weather.get_current_weather(37.5665, 126.9780))

    assert captured_params["serviceKey"] == "dedicated-key"


def test_get_current_weather_returns_snapshot_and_caches(monkeypatch):
    weather._weather_cache.clear()
    monkeypatch.setattr(weather.settings, "weather_api_key", "fake-key")
    response = _fake_kma_response("1", "22.0")

    mock_get = AsyncMock(return_value=response)
    with patch("httpx.AsyncClient.get", new=mock_get):
        result1 = asyncio.run(weather.get_current_weather(37.5665, 126.9780))
        result2 = asyncio.run(weather.get_current_weather(37.5665, 126.9780))

    assert result1 is not None
    assert result1.condition == "rain"
    assert result1.temp_c == 22.0
    assert result2 is result1  # 캐시에서 그대로 나옴
    assert mock_get.call_count == 1  # 두 번째 호출은 캐시 히트라 외부 호출 없음


def test_get_current_weather_returns_none_on_fetch_failure(monkeypatch):
    weather._weather_cache.clear()
    monkeypatch.setattr(weather.settings, "weather_api_key", "fake-key")

    async def raise_error(*args, **kwargs):
        raise httpx.ConnectError("boom")

    with patch("httpx.AsyncClient.get", new=raise_error):
        result = asyncio.run(weather.get_current_weather(37.5665, 126.9780))
    assert result is None


def test_get_current_weather_returns_none_on_malformed_json(monkeypatch):
    weather._weather_cache.clear()
    monkeypatch.setattr(weather.settings, "weather_api_key", "fake-key")
    request = httpx.Request("GET", weather.KMA_BASE_URL)
    response = httpx.Response(200, request=request, json={"unexpected": "shape"})

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        result = asyncio.run(weather.get_current_weather(37.5665, 126.9780))
    assert result is None
