import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.errors import OcrServiceError, ReportImageFetchError
from app.integrations.gemini import GeminiVisionClient


def _client() -> GeminiVisionClient:
    return GeminiVisionClient(api_key="test-key")


def test_missing_api_key_raises_ocr_service_error():
    client = GeminiVisionClient(api_key="placeholder")
    client._key = ""  # simulate no key configured anywhere, bypassing settings fallback
    with pytest.raises(OcrServiceError):
        asyncio.run(client.extract_from_image("https://example.com/a.jpg"))


def test_image_fetch_404_raises_report_image_fetch_error():
    request = httpx.Request("GET", "https://example.com/missing.jpg")
    response = httpx.Response(404, request=request)
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        with pytest.raises(ReportImageFetchError):
            asyncio.run(_client().extract_from_image("https://example.com/missing.jpg"))


def test_non_image_content_type_raises_report_image_fetch_error():
    request = httpx.Request("GET", "https://example.com/page.html")
    response = httpx.Response(
        200, request=request, content=b"<html></html>", headers={"content-type": "text/html"}
    )
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        with pytest.raises(ReportImageFetchError):
            asyncio.run(_client().extract_from_image("https://example.com/page.html"))


def test_generate_content_failure_raises_ocr_service_error():
    get_request = httpx.Request("GET", "https://example.com/a.jpg")
    get_response = httpx.Response(
        200, request=get_request, content=b"fake-bytes", headers={"content-type": "image/jpeg"}
    )
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(503, request=post_request)
    with (
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=get_response)),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)),
    ):
        with pytest.raises(OcrServiceError):
            asyncio.run(_client().extract_from_image("https://example.com/a.jpg"))


def _mock_gemini_reply(get_response, text: str):
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
    )
    return (
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=get_response)),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)),
    )


_ROUTE_STOPS = [
    {"place_name": "국밥집", "category": "discount", "final_price": 8000.0, "savings_rate": 20.0},
]


def test_summarize_route_returns_none_when_api_key_missing():
    client = GeminiVisionClient(api_key="placeholder")
    client._key = ""
    result = asyncio.run(
        client.summarize_route(_ROUTE_STOPS, budget=20000, party_size=1, total_spend=8000, total_savings=2000)
    )
    assert result is None


def test_summarize_route_returns_none_on_http_failure():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(503, request=post_request)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(
            _client().summarize_route(
                _ROUTE_STOPS, budget=20000, party_size=1, total_spend=8000, total_savings=2000
            )
        )
    assert result is None


def test_summarize_route_returns_stripped_text_on_success():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": "  국밥집에서 8,000원만 써요.  "}]}}]},
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(
            _client().summarize_route(
                _ROUTE_STOPS, budget=20000, party_size=1, total_spend=8000, total_savings=2000
            )
        )
    assert result == "국밥집에서 8,000원만 써요."


def test_extract_menu_items_parses_json_array_and_drops_incomplete_rows():
    get_request = httpx.Request("GET", "https://example.com/menu.jpg")
    get_response = httpx.Response(
        200, request=get_request, content=b"fake-bytes", headers={"content-type": "image/jpeg"}
    )
    reply = (
        '[{"name": "아메리카노", "price": 3500}, '
        '{"name": "빠진 가격"}, '
        '{"price": 1000}]'
    )
    get_patch, post_patch = _mock_gemini_reply(get_response, reply)
    with get_patch, post_patch:
        items = asyncio.run(_client().extract_menu_items("https://example.com/menu.jpg"))

    assert len(items) == 1
    assert items[0].name == "아메리카노"
    assert items[0].price == 3500.0


def test_extract_menu_items_returns_empty_list_on_malformed_response():
    get_request = httpx.Request("GET", "https://example.com/menu.jpg")
    get_response = httpx.Response(
        200, request=get_request, content=b"fake-bytes", headers={"content-type": "image/jpeg"}
    )
    get_patch, post_patch = _mock_gemini_reply(get_response, "이 사진에서는 메뉴를 찾을 수 없어요")
    with get_patch, post_patch:
        items = asyncio.run(_client().extract_menu_items("https://example.com/menu.jpg"))

    assert items == []
