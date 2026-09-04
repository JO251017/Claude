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


# --- 인증키 유출 방지(2026-09-02) --- 운영 로그에서 Gemini 키가 평문으로
# 노출된 것을 확인하고(httpx가 요청 URL 전체를 INFO로 남기는데 키를 쿼리
# 파라미터로 보내고 있었음) 키를 헤더로 옮겼다. 아래 두 테스트는 그 조치가
# 나중에 조용히 되돌아가는 걸 막는다 — 키가 URL에 다시 들어가면 로그·예외
# 메시지·트레이스백 세 경로로 동시에 새기 때문에 회귀 비용이 크다.


def test_api_key_is_sent_as_header_not_in_url():
    captured: dict = {}

    async def fake_post(self, url, **kwargs):
        captured["url"] = str(url)
        captured["params"] = kwargs.get("params")
        captured["headers"] = kwargs.get("headers") or {}
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )

    with patch("httpx.AsyncClient.post", new=fake_post):
        asyncio.run(_client()._ask_text("hello"))

    assert captured["headers"].get("x-goog-api-key") == "test-key"
    # 키가 URL이나 쿼리 파라미터 어디에도 실리면 안 된다.
    assert "test-key" not in captured["url"]
    assert "key" not in (captured["params"] or {})


def test_http_client_url_logging_is_silenced():
    """httpx의 INFO 요청 로그(URL 전체 포함)가 꺼져 있어야 한다 — 헤더 인증을
    지원하지 않는 공공 API(serviceKey를 쿼리로만 받음)까지 한 번에 덮는 방어선."""
    import logging

    from app.core.observability import configure_logging

    configure_logging()
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert not logging.getLogger("httpcore").isEnabledFor(logging.INFO)


# --- 통상가 배치 추정(2026-09-04) --- 호출 수를 줄이려고 여러 메뉴를 한 번에
# 묻는다. 응답 정렬이 어긋나면 엉뚱한 메뉴에 엉뚱한 가격이 붙어 틀린 절약률을
# 만들어내므로, 번호 대조가 실제로 걸리는지 고정해둔다.


def _batch_response(text: str):
    async def fake_post(self, url, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200, request=request,
            json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
        )

    return fake_post


def test_batch_estimate_maps_prices_by_index():
    body = '[{"index": 1, "typical_price": 8000}, {"index": 2, "typical_price": 12000}]'
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(
            _client().estimate_typical_prices_batch([("김치찌개", "충남"), ("삼겹살", "충남")])
        )
    assert got == {0: 8000.0, 1: 12000.0}


def test_batch_estimate_drops_out_of_range_index():
    """입력이 2개인데 5번이 오면 응답이 어긋난 것이다 — 억지로 맞추지 않고 버린다."""
    body = '[{"index": 5, "typical_price": 9000}, {"index": 1, "typical_price": 7000}]'
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(_client().estimate_typical_prices_batch([("a", None), ("b", None)]))
    assert got == {0: 7000.0}


def test_batch_estimate_skips_null_and_nonpositive_prices():
    body = (
        '[{"index": 1, "typical_price": null}, {"index": 2, "typical_price": 0},'
        ' {"index": 3, "typical_price": 5000}]'
    )
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(
            _client().estimate_typical_prices_batch([("a", None), ("b", None), ("c", None)])
        )
    assert got == {2: 5000.0}


def test_batch_estimate_returns_empty_on_bad_json_instead_of_raising():
    with patch("httpx.AsyncClient.post", new=_batch_response("설명하자면 8000원쯤입니다")):
        got = asyncio.run(_client().estimate_typical_prices_batch([("a", None)]))
    assert got == {}


def test_batch_estimate_empty_input_makes_no_api_call():
    called = {"n": 0}

    async def counting_post(self, url, **kwargs):  # pragma: no cover - 불리면 안 됨
        called["n"] += 1
        raise AssertionError("빈 입력으로 API를 부르면 안 된다")

    with patch("httpx.AsyncClient.post", new=counting_post):
        assert asyncio.run(_client().estimate_typical_prices_batch([])) == {}
    assert called["n"] == 0


# --- 메뉴명 동의어 후보 배치(2026-09-04) --- AI가 "표기만 다른 쌍"을 찾아주는
# 기능. 인덱스 응답을 실제 문자열로 되돌리는 지점이 특히 중요하다 — 여기가
# 어긋나면 엉뚱한 메뉴 쌍이 후보로 잘못 쌓인다.


def test_synonym_batch_maps_indexes_back_to_names():
    body = '[{"variant_index": 2, "canonical_index": 1, "reason": "표기 차이"}]'
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(_client().suggest_menu_synonyms_batch(["커트", "컷트"]))
    assert got == [("컷트", "커트", "표기 차이")]


def test_synonym_batch_drops_self_pair_and_out_of_range():
    body = (
        '[{"variant_index": 1, "canonical_index": 1, "reason": "자기 자신"},'
        ' {"variant_index": 9, "canonical_index": 1, "reason": "범위 밖"},'
        ' {"variant_index": 2, "canonical_index": 1, "reason": "정상"}]'
    )
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(_client().suggest_menu_synonyms_batch(["커트", "컷트"]))
    assert got == [("컷트", "커트", "정상")]


def test_synonym_batch_empty_result_is_fine():
    with patch("httpx.AsyncClient.post", new=_batch_response("[]")):
        got = asyncio.run(_client().suggest_menu_synonyms_batch(["커트", "컷트"]))
    assert got == []


def test_synonym_batch_bad_json_returns_empty_instead_of_raising():
    with patch("httpx.AsyncClient.post", new=_batch_response("음... 잘 모르겠어요")):
        got = asyncio.run(_client().suggest_menu_synonyms_batch(["커트", "컷트"]))
    assert got == []


def test_synonym_batch_single_name_makes_no_api_call():
    called = {"n": 0}

    async def counting_post(self, url, **kwargs):  # pragma: no cover - 불리면 안 됨
        called["n"] += 1
        raise AssertionError("이름 1개로는 짝을 지을 수 없다")

    with patch("httpx.AsyncClient.post", new=counting_post):
        assert asyncio.run(_client().suggest_menu_synonyms_batch(["커트"])) == []
    assert called["n"] == 0


# --- 프랜차이즈 매칭 키워드 제안 배치(2026-09-04) --- AI가 브랜드별 표기
# 변형을 찾아주는 기능. 인덱스가 어긋나면 엉뚱한 브랜드에 키워드가 붙는다 —
# 브랜드 매칭이 넓어지면 엉뚱한 매장에 그 브랜드 가격이 붙어버리므로 특히
# 보수적으로 검증해야 한다.


def test_franchise_keyword_batch_maps_index_back_to_brand():
    body = '[{"index": 2, "keywords": ["이디야커피", "ediya"]}]'
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(
            _client().suggest_franchise_keywords_batch([("스타벅스", None), ("이디야", None)])
        )
    assert got == {1: ["이디야커피", "ediya"]}


def test_franchise_keyword_batch_drops_out_of_range_index():
    body = (
        '[{"index": 9, "keywords": ["범위밖"]}, {"index": 1, "keywords": ["starbucks"]}]'
    )
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(_client().suggest_franchise_keywords_batch([("스타벅스", None)]))
    assert got == {0: ["starbucks"]}


def test_franchise_keyword_batch_drops_empty_keyword_list():
    body = '[{"index": 1, "keywords": []}]'
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(_client().suggest_franchise_keywords_batch([("스타벅스", None)]))
    assert got == {}


def test_franchise_keyword_batch_caps_at_three_and_strips_blanks():
    body = '[{"index": 1, "keywords": ["a", "  ", "b", "c", "d"]}]'
    with patch("httpx.AsyncClient.post", new=_batch_response(body)):
        got = asyncio.run(_client().suggest_franchise_keywords_batch([("스타벅스", None)]))
    assert got == {0: ["a", "b", "c"]}


def test_franchise_keyword_batch_empty_result_is_fine():
    with patch("httpx.AsyncClient.post", new=_batch_response("[]")):
        got = asyncio.run(_client().suggest_franchise_keywords_batch([("스타벅스", None)]))
    assert got == {}


def test_franchise_keyword_batch_bad_json_returns_empty_instead_of_raising():
    with patch("httpx.AsyncClient.post", new=_batch_response("음... 잘 모르겠어요")):
        got = asyncio.run(_client().suggest_franchise_keywords_batch([("스타벅스", None)]))
    assert got == {}


def test_franchise_keyword_batch_empty_input_makes_no_api_call():
    called = {"n": 0}

    async def counting_post(self, url, **kwargs):  # pragma: no cover - 불리면 안 됨
        called["n"] += 1
        raise AssertionError("빈 입력으로 API를 부르면 안 된다")

    with patch("httpx.AsyncClient.post", new=counting_post):
        assert asyncio.run(_client().suggest_franchise_keywords_batch([])) == {}
    assert called["n"] == 0


# --- 제보 사진 품질 사전 신호(2026-09-04) --- extract_from_image 응답에
# looks_usable/quality_note를 얹어서, 관련 없거나 흐린 사진을 제출 전에
# 부드럽게 알려줄 수 있게 한다. **차단은 아니다** — 이 신호로 제보를 막지
# 않는다(파이프라인은 그대로 즉시 게시).


def _image_response(body_json_text: str):
    async def fake_get(self, url, **kwargs):
        return httpx.Response(
            200, request=httpx.Request("GET", url),
            content=b"fake-bytes", headers={"content-type": "image/jpeg"},
        )

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200, request=httpx.Request("POST", url),
            json={"candidates": [{"content": {"parts": [{"text": body_json_text}]}}]},
        )

    return fake_get, fake_post


def test_extract_from_image_reads_quality_signal_when_unusable():
    body = '{"title": null, "price": null, "category": null, "looks_usable": false, "quality_note": "사진이 흐려서 글자가 안 보여요"}'
    get_fn, post_fn = _image_response(body)
    with patch("httpx.AsyncClient.get", new=get_fn), patch("httpx.AsyncClient.post", new=post_fn):
        result = asyncio.run(_client().extract_from_image("https://example.com/a.jpg"))
    assert result.looks_usable is False
    assert result.quality_note == "사진이 흐려서 글자가 안 보여요"


def test_extract_from_image_quality_signal_defaults_to_none_when_absent():
    """모델이 필드를 아예 안 주면 "모름"이어야 한다 — "나쁨"으로 잘못 해석해서
    없는 경고를 보여주면 안 된다."""
    body = '{"title": "아메리카노", "price": 4000, "category": "food"}'
    get_fn, post_fn = _image_response(body)
    with patch("httpx.AsyncClient.get", new=get_fn), patch("httpx.AsyncClient.post", new=post_fn):
        result = asyncio.run(_client().extract_from_image("https://example.com/a.jpg"))
    assert result.looks_usable is None
    assert result.quality_note is None


def test_extract_from_image_ignores_empty_quality_note():
    body = '{"title": null, "price": null, "category": null, "looks_usable": true, "quality_note": ""}'
    get_fn, post_fn = _image_response(body)
    with patch("httpx.AsyncClient.get", new=get_fn), patch("httpx.AsyncClient.post", new=post_fn):
        result = asyncio.run(_client().extract_from_image("https://example.com/a.jpg"))
    assert result.looks_usable is True
    assert result.quality_note is None
