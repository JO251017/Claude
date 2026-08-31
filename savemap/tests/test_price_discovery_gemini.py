import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.integrations.gemini import GeminiVisionClient, GroundingCitation, GroundingUnavailableError


def _client() -> GeminiVisionClient:
    return GeminiVisionClient(api_key="test-key")


def _post_response(body: dict, status: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    return httpx.Response(status, request=request, json=body)


# --- ground_search ---


def test_ground_search_raises_without_key():
    # 실사용 중 발견(2026-08-31): 이전엔 이 경우와 "요청은 성공했지만 자료 없음"이
    # 똑같이 None 하나로 뭉개져서 관리자 페이지에서 구분이 안 됐다 — 이제 이 경우는
    # 예외로, "정말 자료가 없음"은 citations=[]인 정상 결과로 구분한다.
    client = GeminiVisionClient(api_key="")
    with pytest.raises(GroundingUnavailableError) as exc_info:
        asyncio.run(client.ground_search("아무 매장 메뉴 가격"))
    assert exc_info.value.reason == "NO_API_KEY"


def test_ground_search_parses_text_and_citations():
    body = {
        "candidates": [
            {
                "content": {"parts": [{"text": "김치찌개는 8,000원으로 확인됩니다."}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"uri": "https://example.com/menu", "title": "공식 메뉴"}},
                        {"web": {"uri": "https://blog.example.com/post"}},  # title 없는 경우
                    ]
                },
            }
        ]
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_post_response(body))):
        result = asyncio.run(_client().ground_search("냉삼 주소 메뉴 가격"))
    assert result is not None
    assert "8,000원" in result.text
    assert result.citations == [
        GroundingCitation(url="https://example.com/menu", title="공식 메뉴"),
        GroundingCitation(url="https://blog.example.com/post", title="https://blog.example.com/post"),
    ]


def test_ground_search_raises_with_reason_on_connection_failure():
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("boom"))):
        with pytest.raises(GroundingUnavailableError) as exc_info:
            asyncio.run(_client().ground_search("냉삼 메뉴 가격"))
    assert exc_info.value.reason == "ConnectError"


def test_ground_search_raises_with_status_code_on_http_error():
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(return_value=_post_response({"error": "nope"}, status=500)),
    ):
        with pytest.raises(GroundingUnavailableError) as exc_info:
            asyncio.run(_client().ground_search("냉삼 메뉴 가격"))
    assert exc_info.value.reason == "HTTP_500"


def test_ground_search_raises_on_unexpected_response_shape():
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_post_response({"candidates": []}))):
        with pytest.raises(GroundingUnavailableError) as exc_info:
            asyncio.run(_client().ground_search("냉삼 메뉴 가격"))
    assert exc_info.value.reason == "BAD_RESPONSE_SHAPE"


def test_ground_search_with_no_grounding_chunks_has_empty_citations():
    body = {"candidates": [{"content": {"parts": [{"text": "못 찾았어요"}]}}]}
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_post_response(body))):
        result = asyncio.run(_client().ground_search("아무 데나"))
    assert result is not None
    assert result.citations == []


# --- extract_price_discovery ---

_CITATIONS = [GroundingCitation(url="https://example.com/menu", title="공식 메뉴")]


def _extraction_response_text(payload: dict) -> httpx.Response:
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
    return _post_response(body)


def test_extract_price_discovery_normal_case_is_saved():
    payload = {
        "store_match": {"matched": True, "confidence": 0.97, "reason": "이름/주소 일치"},
        "prices": [
            {
                "menu_name": "김치찌개",
                "price": 8000,
                "currency": "KRW",
                "source_type": "official",
                "source_url": "https://example.com/menu",
                "source_title": "공식 메뉴",
                "observed_at": "2026-08-30",
                "evidence": "공식 메뉴 페이지에서 확인",
            }
        ],
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_extraction_response_text(payload))):
        result = asyncio.run(
            _client().extract_price_discovery("가게", "주소", "한식", "본문", _CITATIONS)
        )
    assert result is not None
    assert result.store_match.matched is True
    assert len(result.prices) == 1
    assert result.prices[0].menu_name == "김치찌개"
    assert result.prices[0].price == 8000.0


def test_extract_price_discovery_no_prices_returns_empty_list():
    payload = {"store_match": {"matched": True, "confidence": 0.9, "reason": "일치"}, "prices": []}
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_extraction_response_text(payload))):
        result = asyncio.run(
            _client().extract_price_discovery("가게", "주소", "한식", "본문", _CITATIONS)
        )
    assert result is not None
    assert result.prices == []


def test_extract_price_discovery_rejects_price_without_number():
    # "보통 8천원 정도" 같은 자연어 추정값은애초에 price 필드가 숫자가 아니므로 버려진다
    # — 지어낸 값을 저장하지 않는다.
    payload = {
        "store_match": {"matched": True, "confidence": 0.9, "reason": "일치"},
        "prices": [
            {
                "menu_name": "김치찌개",
                "price": "보통 8천원 정도",
                "source_type": "web",
                "source_url": "https://example.com/menu",
            }
        ],
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_extraction_response_text(payload))):
        result = asyncio.run(
            _client().extract_price_discovery("가게", "주소", "한식", "본문", _CITATIONS)
        )
    assert result is not None
    assert result.prices == []


def test_extract_price_discovery_rejects_price_not_from_cited_url():
    # source_url이 이번 그라운딩에서 실제로 인용된 URL 목록에 없으면(모델이
    # 지어냈거나 다른 자료를 섞음) 버린다.
    payload = {
        "store_match": {"matched": True, "confidence": 0.9, "reason": "일치"},
        "prices": [
            {
                "menu_name": "김치찌개",
                "price": 8000,
                "source_type": "web",
                "source_url": "https://not-cited.example.com/",
            }
        ],
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_extraction_response_text(payload))):
        result = asyncio.run(
            _client().extract_price_discovery("가게", "주소", "한식", "본문", _CITATIONS)
        )
    assert result is not None
    assert result.prices == []


def test_extract_price_discovery_store_match_false_still_parses():
    # 매장 동일성이 불확실하면 matched=false — 이 함수는 그 판단을 그대로 전달만
    # 하고(거절 여부 결정은 store_matcher.py의 역할), 가격이 있어도 파싱은 된다.
    payload = {
        "store_match": {"matched": False, "confidence": 0.3, "reason": "동일 이름의 다른 지점일 수 있음"},
        "prices": [
            {
                "menu_name": "김치찌개",
                "price": 8000,
                "source_type": "web",
                "source_url": "https://example.com/menu",
            }
        ],
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_extraction_response_text(payload))):
        result = asyncio.run(
            _client().extract_price_discovery("가게", "주소", "한식", "본문", _CITATIONS)
        )
    assert result is not None
    assert result.store_match.matched is False
    assert len(result.prices) == 1  # 파싱은 됨 — 거절은 store_matcher가 결정


def test_extract_price_discovery_returns_none_on_malformed_json():
    body = {"candidates": [{"content": {"parts": [{"text": "이건 JSON이 아니에요"}]}}]}
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_post_response(body))):
        result = asyncio.run(
            _client().extract_price_discovery("가게", "주소", "한식", "본문", _CITATIONS)
        )
    assert result is None


def test_extract_price_discovery_confidence_is_clamped_to_0_1():
    payload = {"store_match": {"matched": True, "confidence": 1.5, "reason": "확신"}, "prices": []}
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_extraction_response_text(payload))):
        result = asyncio.run(
            _client().extract_price_discovery("가게", "주소", "한식", "본문", _CITATIONS)
        )
    assert result is not None
    assert result.store_match.confidence == 1.0
