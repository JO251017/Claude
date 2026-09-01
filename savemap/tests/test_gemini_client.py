import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.errors import OcrServiceError, ReportImageFetchError
from app.integrations.gemini import (
    GeminiVisionClient,
    _digest_prompt,
    _offer_blurb_prompt,
    _route_summary_prompt,
    _typical_price_prompt,
)


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
    # 두 번 다 503이면(재시도 포함) 결국 OcrServiceError로 끝나야 한다 —
    # AsyncMock의 return_value는 매 호출마다 같은 503을 재사용하므로 재시도가
    # 있어도 최종 결과는 그대로 실패다.
    get_request = httpx.Request("GET", "https://example.com/a.jpg")
    get_response = httpx.Response(
        200, request=get_request, content=b"fake-bytes", headers={"content-type": "image/jpeg"}
    )
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(503, request=post_request)
    with (
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=get_response)),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(OcrServiceError):
            asyncio.run(_client().extract_from_image("https://example.com/a.jpg"))


# --- 일시 과부하(429/503) 자동 재시도(2026-08-30) — 프로덕션에서 발견하기/추천은
# 1초 안에 됐는데 사진 분석만 Gemini 쪽 503으로 15초 넘게 걸리다 실패한 사례를
# 확인하고 추가. ---


def test_generate_content_retries_once_on_503_then_succeeds():
    get_request = httpx.Request("GET", "https://example.com/a.jpg")
    get_response = httpx.Response(
        200, request=get_request, content=b"fake-bytes", headers={"content-type": "image/jpeg"}
    )
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    fail_response = httpx.Response(503, request=post_request)
    ok_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": '{"price": 1000}'}]}}]},
    )
    mock_post = AsyncMock(side_effect=[fail_response, ok_response])
    mock_sleep = AsyncMock()
    with (
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=get_response)),
        patch("httpx.AsyncClient.post", new=mock_post),
        patch("asyncio.sleep", new=mock_sleep),
    ):
        result = asyncio.run(_client().extract_from_image("https://example.com/a.jpg"))

    assert result.price == 1000
    assert mock_post.call_count == 2  # 재시도로 두 번째 시도에서 성공
    mock_sleep.assert_awaited_once()


def test_generate_content_retries_once_on_429_then_succeeds():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    fail_response = httpx.Response(429, request=post_request)
    ok_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": "설명 문장"}]}}]},
    )
    mock_post = AsyncMock(side_effect=[fail_response, ok_response])
    with (
        patch("httpx.AsyncClient.post", new=mock_post),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = asyncio.run(
            _client().summarize_route(
                _ROUTE_STOPS, budget=20000, party_size=1, total_spend=8000, total_savings=2000
            )
        )
    assert result == "설명 문장"
    assert mock_post.call_count == 2


def test_generate_content_does_not_retry_non_retryable_status():
    # 400(잘못된 요청) 같은 건 재시도해도 똑같이 실패할 뿐이니 딱 한 번만 부른다.
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    bad_response = httpx.Response(400, request=post_request)
    mock_post = AsyncMock(return_value=bad_response)
    mock_sleep = AsyncMock()
    with (
        patch("httpx.AsyncClient.post", new=mock_post),
        patch("asyncio.sleep", new=mock_sleep),
    ):
        result = asyncio.run(
            _client().summarize_route(
                _ROUTE_STOPS, budget=20000, party_size=1, total_spend=8000, total_savings=2000
            )
        )
    assert result is None  # summarize_route는 fail-soft로 None
    assert mock_post.call_count == 1
    mock_sleep.assert_not_awaited()


def test_generate_content_retries_on_network_error_then_succeeds():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    ok_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": "복구됨"}]}}]},
    )
    mock_post = AsyncMock(side_effect=[httpx.ConnectTimeout("boom"), ok_response])
    with (
        patch("httpx.AsyncClient.post", new=mock_post),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = asyncio.run(
            _client().summarize_route(
                _ROUTE_STOPS, budget=20000, party_size=1, total_spend=8000, total_savings=2000
            )
        )
    assert result == "복구됨"
    assert mock_post.call_count == 2


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


# --- generate_offer_blurb / _offer_blurb_prompt (AI 활용 확대 안건 D, 2026-08-31)
# — summarize_route와 완전히 같은 fail-soft 계약(요청 실패 시 None, 성공 시
# strip된 텍스트)이라 같은 테스트 패턴을 그대로 따른다. ---

_OFFER_FACTS = {"업종": "한식", "가격 비교 기준": "주변 매장 실측가", "비교한 주변 매장 수": "8곳"}


def test_generate_offer_blurb_returns_none_when_api_key_missing():
    client = GeminiVisionClient(api_key="placeholder")
    client._key = ""
    result = asyncio.run(client.generate_offer_blurb(_OFFER_FACTS))
    assert result is None


def test_generate_offer_blurb_returns_none_on_http_failure():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(503, request=post_request)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(_client().generate_offer_blurb(_OFFER_FACTS))
    assert result is None


def test_generate_offer_blurb_returns_stripped_text_on_success():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": "  주변보다 저렴해요.  "}]}}]},
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(_client().generate_offer_blurb(_OFFER_FACTS))
    assert result == "주변보다 저렴해요."


def test_offer_blurb_prompt_includes_every_fact():
    prompt = _offer_blurb_prompt(_OFFER_FACTS)
    assert "한식" in prompt
    assert "주변 매장 실측가" in prompt
    assert "8곳" in prompt


def test_offer_blurb_prompt_forbids_new_numbers():
    prompt = _offer_blurb_prompt(_OFFER_FACTS)
    assert "새로 만들어" in prompt


# --- generate_digest / _digest_prompt (AI 활용 확대 안건 C, 2026-08-31) —
# generate_offer_blurb와 완전히 같은 fail-soft 계약. ---

_DIGEST_FACTS = {"이번 주 절약액": "8000원", "연속 활동 일수": "5일"}


def test_generate_digest_returns_none_when_api_key_missing():
    client = GeminiVisionClient(api_key="placeholder")
    client._key = ""
    result = asyncio.run(client.generate_digest(_DIGEST_FACTS))
    assert result is None


def test_generate_digest_returns_none_on_http_failure():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(503, request=post_request)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(_client().generate_digest(_DIGEST_FACTS))
    assert result is None


def test_generate_digest_returns_stripped_text_on_success():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": "  이번 주도 잘하셨어요!  "}]}}]},
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(_client().generate_digest(_DIGEST_FACTS))
    assert result == "이번 주도 잘하셨어요!"


def test_digest_prompt_includes_every_fact():
    prompt = _digest_prompt(_DIGEST_FACTS)
    assert "8000원" in prompt
    assert "5일" in prompt


def test_digest_prompt_forbids_new_numbers():
    prompt = _digest_prompt(_DIGEST_FACTS)
    assert "새로 만들어" in prompt


# --- 통상가 지역 세분화(2026-09-01, §26~27) ---


def test_typical_price_prompt_includes_region_when_given():
    prompt = _typical_price_prompt("김치찌개", "충남")
    assert "지역: 충남" in prompt


def test_typical_price_prompt_omits_region_when_none():
    prompt = _typical_price_prompt("김치찌개")
    assert "지역:" not in prompt


def test_estimate_typical_price_forwards_region_into_prompt():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": '{"typical_price": 9000}'}]}}]},
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)) as mock_post:
        result = asyncio.run(_client().estimate_typical_price("김치찌개", "충남"))
    assert result == 9000.0
    sent_prompt = mock_post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "지역: 충남" in sent_prompt


def test_estimate_typical_price_without_region_matches_old_behavior():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": '{"typical_price": 9000}'}]}}]},
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(_client().estimate_typical_price("김치찌개"))
    assert result == 9000.0


# --- 펫 레벨업 대사(AI MVP §D, 2026-09-01) ---


def test_generate_pet_levelup_line_returns_none_when_api_key_missing():
    client = GeminiVisionClient(api_key="placeholder")
    client._key = ""
    result = asyncio.run(client.generate_pet_levelup_line("산책 나온 강아지"))
    assert result is None


def test_generate_pet_levelup_line_returns_none_on_http_failure():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(503, request=post_request)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(_client().generate_pet_levelup_line("산책 나온 강아지"))
    assert result is None


def test_generate_pet_levelup_line_returns_stripped_text_on_success():
    post_request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    post_response = httpx.Response(
        200,
        request=post_request,
        json={"candidates": [{"content": {"parts": [{"text": "  신난다!  "}]}}]},
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_response)):
        result = asyncio.run(_client().generate_pet_levelup_line("산책 나온 강아지"))
    assert result == "신난다!"
