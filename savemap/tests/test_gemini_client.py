import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.errors import OcrServiceError, ReportImageFetchError
from app.integrations.gemini import GeminiVisionClient, _route_summary_prompt


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


def test_route_summary_prompt_includes_context_note_when_given():
    # context_note(사용자가 고른 활동/조건)는 "설명 근거"로만 프롬프트에 들어가야
    # 한다 — 없으면 프롬프트에서 아예 빠져야 하고(기존 동작 보존), 있으면 문구가
    # 그대로 나타나야 한다.
    prompt = _route_summary_prompt(
        _ROUTE_STOPS, budget=20000, party_size=1, total_spend=8000, total_savings=2000,
        context_note="활동: 식사, 커피 · 조건: 검증된 정보 우선",
    )
    assert "활동: 식사, 커피 · 조건: 검증된 정보 우선" in prompt


def test_route_summary_prompt_omits_context_note_when_none():
    prompt = _route_summary_prompt(
        _ROUTE_STOPS, budget=20000, party_size=1, total_spend=8000, total_savings=2000
    )
    assert "사용자가 고른 조건:" not in prompt


def test_summarize_route_forwards_context_note_into_prompt():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": "설명 문장"}]}}]},
    )
    mock_post = AsyncMock(return_value=post_response)
    with patch("httpx.AsyncClient.post", new=mock_post):
        result = asyncio.run(
            _client().summarize_route(
                _ROUTE_STOPS,
                budget=20000,
                party_size=1,
                total_spend=8000,
                total_savings=2000,
                context_note="활동: 식사",
            )
        )
    assert result == "설명 문장"
    sent_prompt = mock_post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "활동: 식사" in sent_prompt


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
