import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.errors import OcrServiceError, ReportImageFetchError
from app.domain.enums import Category

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com"
GEMINI_MODEL = "gemini-flash-latest"
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# 사진 분석 재시도(2026-08-30) — 프로덕션에서 발견하기/추천은 1초 안에 잘 됐는데
# 사진 분석만 Gemini 쪽 일시 과부하(503)로 15초 넘게 걸리다 실패한 사례를 로그로
# 확인했다. 429(속도제한)도 같은 성격 — 재시도하면 성공할 가능성이 있다. 그 외
# 4xx(잘못된 키 등)는 몇 번을 다시 불러도 똑같이 실패할 뿐이라 재시도하지 않는다.
_RETRYABLE_STATUS = {429, 503}
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SEC = 1.5
# 429는 구글이 Retry-After 헤더로 "몇 초 뒤에 다시 해라"를 직접 알려주기도 한다 —
# 그 값이 있으면 고정 1.5초 대신 그 값을 따른다(2026-08-31, 그라운딩 429 연속
# 실패 진단 중 추가). Render 무료 플랜 요청 타임아웃을 넘기지 않도록 상한을 둔다
# — 헤더가 너무 크면(예: 분당 한도라 60초+) 어차피 이번 요청 안에서 기다려봐야
# 소용없으니 상한까지만 쉬고 다음 재시도(그래도 실패하면 그대로 실패 처리)로 넘어간다.
_MAX_RETRY_AFTER_SEC = 8.0


def _retry_delay_seconds(resp: httpx.Response) -> float:
    """Retry-After 헤더가 있고 유효한 정수 초면 그 값(상한 적용)을, 없거나
    파싱이 안 되면 기존 고정 지연을 그대로 쓴다 — 구글이 Retry-After를 안 주는
    경우(대부분의 503, 일부 429)도 있으므로 fallback은 항상 유지한다."""
    raw = resp.headers.get("retry-after")
    if raw is None:
        return _RETRY_DELAY_SEC
    try:
        seconds = float(raw)
    except ValueError:
        return _RETRY_DELAY_SEC
    if seconds <= 0:
        return _RETRY_DELAY_SEC
    return min(seconds, _MAX_RETRY_AFTER_SEC)


def _extract_error_detail(resp: httpx.Response) -> str | None:
    """구글 에러 응답 본문에서 사람이 읽을 요약을 뽑는다 — 특히 429는
    {"error": {"status": "RESOURCE_EXHAUSTED", "message": "...", "details": [...]}}
    형태로 어떤 quota가 초과됐는지까지 실어 보내는 경우가 많다(2026-08-31,
    그라운딩 429 원인 규명용으로 추가). 본문이 JSON이 아니거나 예상과 다른
    구조여도 예외를 던지지 않고 최대한 남은 텍스트라도 잘라 돌려준다 — 이
    함수 자체의 실패가 원래 에러 처리를 가리면 안 된다."""
    try:
        body = resp.json()
    except (json.JSONDecodeError, ValueError):
        text = (resp.text or "").strip()
        return text[:300] if text else None

    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return str(body)[:300]

    parts = []
    if error.get("status"):
        parts.append(str(error["status"]))
    if error.get("message"):
        parts.append(str(error["message"]))
    # QuotaFailure details는 어떤 quota가 초과됐는지(quotaId/quotaMetric)를
    # 담고 있어서, "429가 났다"보다 "정확히 뭐가 초과됐다"를 알려준다.
    for d in error.get("details") or []:
        if isinstance(d, dict) and d.get("@type", "").endswith("QuotaFailure"):
            for violation in d.get("violations") or []:
                metric = violation.get("quotaMetric") or violation.get("quotaId")
                if metric:
                    parts.append(f"quota={metric}")
            break

    summary = " · ".join(parts) if parts else str(error)
    return summary[:300] if summary else None

_VALID_CATEGORIES = {c.value for c in Category}

_EXTRACTION_PROMPT = (
    "이 이미지(영수증, 전단지, 매장 사진 등)에서 절약 정보를 추출해줘. "
    "반드시 아래 JSON 형식으로만 응답하고 다른 텍스트는 포함하지 마:\n"
    '{"title": "혜택/상품명", "price": 숫자 또는 null, '
    f'"category": {sorted(_VALID_CATEGORIES)} 중 하나, '
    '"location_text": "이미지에서 보이는 가게 이름이나 주소가 있으면 그 텍스트, 없으면 null"}'
)


# 메뉴판뿐 아니라 영수증도 받는다. 메뉴판을 찍으려면 가게 안에서 대놓고 촬영해야 해서
# 심리적 장벽이 큰데, 영수증은 이미 손에 있고 나와서 찍어도 된다 — 가격 데이터를 실제로
# 모으려면 이쪽이 훨씬 현실적인 경로다. 다만 영수증은 "수량 × 단가 = 금액" 형태라
# 합계 금액을 그대로 단가로 읽으면 가격이 부풀려지므로 단가를 달라고 명시한다.
_MENU_EXTRACTION_PROMPT = (
    "이 이미지는 식당/카페의 메뉴판, 메뉴 사진, 또는 영수증이야. 보이는 모든 메뉴 이름과 "
    "1인분(1개) 기준 단가를 추출해줘.\n"
    "- 영수증이면 수량이 2 이상인 항목은 합계 금액이 아니라 단가(합계÷수량)를 써줘.\n"
    "- 가격을 알아볼 수 없는 항목, 합계·부가세·봉사료·할인 같은 메뉴가 아닌 줄은 제외해.\n"
    "반드시 아래 JSON 배열 형식으로만 응답하고 다른 텍스트는 포함하지 마:\n"
    '[{"name": "메뉴명", "price": 숫자}, ...]'
)


def _price_update_review_prompt(
    item_name: str, old_price: float, old_verified_at: str, new_price: float
) -> str:
    return (
        f'이 사진은 "{item_name}" 메뉴의 가격표·메뉴판·영수증이야. '
        f"SaveMap에는 이미 {old_price:,.0f}원으로 등록돼 있고(마지막 확인: {old_verified_at}), "
        f"이번에 새로 {new_price:,.0f}원이라고 제보됐어. "
        "이 사진이 실제로 그 새 가격을 보여주는 게 맞는지 확인하고, 기존 등록 가격을 이 "
        "사진 기준으로 갱신하는 게 타당한지 판단해줘. 사진이 흐릿하거나, 이 메뉴가 아닌 "
        "다른 걸 찍었거나, 가격이 사진에서 안 보이면 거부해. "
        "반드시 아래 JSON 형식으로만 응답하고 다른 텍스트는 포함하지 마:\n"
        '{"accept_update": true 또는 false, "reason": "한 문장 이유(한국어)"}'
    )


def _typical_price_prompt(item_name: str) -> str:
    return (
        f'한국의 동네 식당/카페에서 "{item_name}"과(와) 같은 메뉴를 판매한다면, '
        "일반적으로 얼마 정도에 판매될지 대략적인 통상 가격을 알려줘. "
        "이건 특정 매장이나 지역의 실제 조사 데이터가 아니라 참고용 짐작이라는 걸 감안해서, "
        "합리적으로 짐작할 수 있으면 원 단위 숫자로, 메뉴 이름이 너무 모호하거나 "
        "짐작이 무의미하면 null로 답해줘. "
        '반드시 아래 JSON 형식으로만 응답하고 다른 텍스트는 포함하지 마:\n'
        '{"typical_price": 숫자 또는 null}'
    )


def _route_summary_prompt(
    stops: list[dict],
    budget: float,
    party_size: int,
    total_spend: float,
    total_savings: float,
    context_note: str | None = None,
) -> str:
    lines = "\n".join(
        f"{i + 1}. {s['place_name']} ({s['category']}) - {s['final_price']:,.0f}원"
        + (f", 평균 대비 {s['savings_rate']:.0f}% 저렴" if s["savings_rate"] > 0 else "")
        for i, s in enumerate(stops)
    )
    # context_note: 사용자가 Step1/Step2에서 고른 활동/조건(예: "활동: 식사, 커피 ·
    # 조건: 검증된 정보 우선") — "왜 이 코스인지" 설명에 참고만 하게 한다. 숫자/장소는
    # 여전히 아래 코스 목록에 있는 것만 쓰라고 명시해서, 참고 정보가 새 숫자를 만들어낼
    # 근거로 오용되지 않게 한다.
    note_line = f"\n사용자가 고른 조건: {context_note}\n" if context_note else ""
    return (
        "아래는 이미 계산이 끝난 절약 코스야. 새로운 숫자나 장소를 절대 만들어내지 말고, "
        "주어진 숫자와 장소 이름만 그대로 사용해서 자연스러운 한국어 한 문단(3문장 이내, "
        "친근한 말투)으로 설명해줘. 사용자가 고른 조건은 왜 이 코스를 추천하는지 "
        "설명하는 데만 참고하고, 그 조건으로 새 숫자를 계산하지는 마. "
        "JSON이 아니라 그냥 문장으로 답해.\n\n"
        f"예산: {budget:,.0f}원 (인원 {party_size}명){note_line}\n코스:\n{lines}\n"
        f"총 지출: {total_spend:,.0f}원\n총 절약: {total_savings:,.0f}원\n"
    )


def _offer_blurb_prompt(facts: dict[str, str]) -> str:
    """AI 활용 확대 안건 D(2026-08-31) — 매장 카드 한 줄 소개. _route_summary_prompt와
    같은 원칙: 숫자/사실은 전부 호출부가 이미 결정해서 준 것만 쓰고, AI는 그걸 자연스러운
    한 문장으로 표현(phrase)만 한다. facts에 없는 숫자를 쓰면 호출부의
    app.engine.ai_text_guard가 그 결과를 통째로 버린다 — 그래도 프롬프트 단계에서부터
    강하게 막아둔다."""
    lines = "\n".join(f"- {k}: {v}" for k, v in facts.items())
    return (
        "아래는 어떤 매장의 절약 정보에 대해 이미 확인된 사실이야. 이 사실 목록에 있는 "
        "것만 근거로, 왜 이 매장이 가볼 만한지 자연스러운 한국어 한 문장(40자 이내, "
        "친근한 말투, 과장·이모지 없이)으로 소개해줘. 목록에 없는 숫자나 사실은 "
        "절대로 새로 만들어 쓰지 마. 매장 이름이나 메뉴 이름은 몰라도 되니 언급하지 마. "
        "JSON이 아니라 그냥 문장으로 답해.\n\n"
        f"사실 목록:\n{lines}\n"
    )


def _strip_code_fence(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def _strip_array_fence(text: str) -> str:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    return match.group(0) if match else text


@dataclass
class OcrResult:
    raw_text: str
    price: float | None
    title: str | None
    category: Category | None
    location_text: str | None = None


@dataclass
class MenuItemGuess:
    name: str
    price: float


class GroundingUnavailableError(Exception):
    """ground_search의 요청 자체가 실패했을 때만 발생시킨다 — "정상 응답인데 결과가
    없었다"(citations가 빈 리스트)와 구분하기 위함. 예전엔 이 둘이 전부 None
    하나로 뭉개져서, 관리자 페이지의 NO_SOURCE_FOUND만 봐서는 "정말 자료가 없는
    매장인지" "요청 자체가 매번 실패하는 설정/네트워크 문제인지" 구분이 안 됐다
    (실사용 중 발견, 2026-08-31 — 실제 매장 3곳이 연속으로 전부 NO_SOURCE_FOUND).
    reason은 32자 error_code 컬럼에 그대로 들어갈 수 있게 짧게 유지한다.

    detail(선택)은 구글이 에러 응답 본문에 실어 보내는 실제 메시지 — 특히 429는
    "RESOURCE_EXHAUSTED"와 함께 어떤 quota가 얼마나 초과됐는지(QuotaFailure)를
    본문에 담아 보내는데, reason(HTTP_429)만으로는 "요청이 잠깐 몰려서인지,
    이 프로젝트에 그라운딩 quota 자체가 없는(예: 결제 미설정) 것인지" 구분이
    안 된다 — 이건 코드로 재현/확인할 수 없고 실제 응답을 봐야만 안다(2026-08-31,
    3개 매장이 매 시도 100% 429로 실패해 원인 규명이 필요해짐). error_code(32자)엔
    안 들어가고 job.result_summary(500자)에 실어서 관리자 페이지에서 바로 읽게 한다."""

    def __init__(self, reason: str, detail: str | None = None):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)


@dataclass
class GroundingCitation:
    url: str
    title: str


@dataclass
class GroundingResult:
    text: str
    citations: list[GroundingCitation]


@dataclass
class PriceDiscoveryStoreMatch:
    matched: bool
    confidence: float
    reason: str


@dataclass
class PriceDiscoveryPriceItem:
    menu_name: str
    price: float
    source_type: str  # "official" | "web" — 지시서 28-13, price_extractor가 이 값을
    # SourceType.S6_AI_DISCOVERY_OFFICIAL/WEB으로 매핑한다(confidence_engine.py).
    source_url: str | None
    source_title: str | None
    observed_at: str | None
    evidence: str | None


@dataclass
class PriceDiscoveryExtraction:
    store_match: PriceDiscoveryStoreMatch
    prices: list[PriceDiscoveryPriceItem]


_PRICE_DISCOVERY_SYSTEM_RULES = (
    "너는 SaveMap 가격 데이터 추출 AI다.\n"
    "목표: 제공된 공개 자료에서 실제 확인 가능한 매장 메뉴와 가격을 구조화한다.\n"
    "규칙:\n"
    "1. 자료에 명시된 가격만 반환한다.\n"
    "2. 가격을 추측하지 않는다.\n"
    "3. 일반적인 시장 가격을 사용하지 않는다.\n"
    "4. 다른 매장의 가격을 현재 매장 가격으로 사용하지 않는다.\n"
    "5. 매장 동일성이 불확실하면 matched=false를 반환한다.\n"
    "6. 메뉴와 가격의 연결이 불확실하면 해당 항목을 제외한다.\n"
    "7. 세트/옵션/2인 메뉴 등은 별도 메뉴로 구분한다.\n"
    "8. 출처 URL을 반드시 반환한다.\n"
    "9. 확인 날짜가 있으면 반환한다.\n"
    "10. 가격이 없으면 빈 배열을 반환한다.\n"
    "11. AI 자신의 지식만으로 가격을 생성하지 않는다.\n"
    "12. 추정값을 실제 가격으로 반환하지 않는다.\n"
)


def _price_discovery_extraction_prompt(
    store_name: str,
    store_address: str | None,
    store_category: str | None,
    grounded_text: str,
    citations: list[GroundingCitation],
) -> str:
    citation_lines = "\n".join(f"- {c.title}: {c.url}" for c in citations) or "(인용 없음)"
    return (
        f"{_PRICE_DISCOVERY_SYSTEM_RULES}\n"
        f"매장 정보:\n이름: {store_name}\n주소: {store_address or '알 수 없음'}\n"
        f"업종: {store_category or '알 수 없음'}\n\n"
        f"검색으로 찾은 자료(요약):\n{grounded_text}\n\n"
        f"인용된 출처:\n{citation_lines}\n\n"
        "출력은 아래 JSON 스키마만 사용하고 다른 텍스트는 포함하지 마:\n"
        '{"store_match": {"matched": true 또는 false, "confidence": 0.0~1.0 사이 숫자, '
        '"reason": "판단 이유"}, '
        '"prices": [{"menu_name": "메뉴명", "price": 숫자, "currency": "KRW", '
        '"source_type": "official 또는 web", "source_url": "위 인용 목록에 있는 URL 중 하나", '
        '"source_title": "출처 제목", "observed_at": "YYYY-MM-DD 또는 null", '
        '"evidence": "이 가격을 확인한 근거 한 문장"}]}'
    )


class GeminiVisionClient:
    def __init__(self, api_key: str | None = None):
        self._key = api_key or settings.gemini_api_key

    async def _post_generate_content(self, client: httpx.AsyncClient, payload: dict) -> dict:
        """generateContent 호출 — 일시 과부하(429/503) 또는 네트워크 오류(타임아웃 등)면
        짧게 쉬었다가 한 번만 더 시도한다. 마지막 시도까지 실패하면(그 상태든, 네트워크
        에러든) 그대로 올려서 호출부의 기존 httpx.HTTPError 처리(OcrServiceError 변환)가
        그대로 먹게 한다 — 재시도 유무와 무관하게 최종 실패 처리 방식은 안 바뀐다."""
        for attempt in range(_MAX_ATTEMPTS):
            is_last = attempt == _MAX_ATTEMPTS - 1
            try:
                resp = await client.post(
                    f"{GEMINI_API_BASE}/v1beta/models/{GEMINI_MODEL}:generateContent",
                    params={"key": self._key},
                    json=payload,
                )
            except httpx.HTTPError:
                if is_last:
                    raise
                await asyncio.sleep(_RETRY_DELAY_SEC)
                continue
            if resp.status_code in _RETRYABLE_STATUS and not is_last:
                await asyncio.sleep(_retry_delay_seconds(resp))
                continue
            resp.raise_for_status()
            return resp.json()
        raise AssertionError("unreachable")  # pragma: no cover — 루프가 항상 return/raise로 끝남

    async def _ask_about_image(self, image_url: str, prompt: str) -> str:
        if not self._key:
            raise OcrServiceError("사진 분석 서비스가 설정되지 않았습니다 (GEMINI_API_KEY 미설정)")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                img_resp = await client.get(image_url)
                img_resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ReportImageFetchError(f"사진을 불러올 수 없습니다: {exc.__class__.__name__}") from exc

            image_bytes = img_resp.content
            mime_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()

            if not mime_type.startswith("image/"):
                raise ReportImageFetchError(
                    f"이미지 파일이 아닙니다 (받은 형식: {mime_type or '알 수 없음'})"
                )
            if len(image_bytes) > MAX_IMAGE_BYTES:
                raise ReportImageFetchError("사진 용량이 너무 큽니다 (최대 10MB)")

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": base64.b64encode(image_bytes).decode(),
                                }
                            },
                        ]
                    }
                ]
            }
            try:
                data = await self._post_generate_content(client, payload)
            except httpx.HTTPError as exc:
                raise OcrServiceError(
                    f"사진 분석 요청에 실패했습니다: {exc.__class__.__name__}"
                ) from exc

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OcrServiceError("사진 분석 결과를 이해할 수 없습니다") from exc

    async def _ask_text(self, prompt: str) -> str:
        if not self._key:
            raise OcrServiceError("AI 서비스가 설정되지 않았습니다 (GEMINI_API_KEY 미설정)")

        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                data = await self._post_generate_content(client, payload)
            except httpx.HTTPError as exc:
                raise OcrServiceError(f"AI 요청에 실패했습니다: {exc.__class__.__name__}") from exc

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OcrServiceError("AI 응답을 이해할 수 없습니다") from exc

    async def ground_search(self, query: str) -> GroundingResult:
        """AI Price Discovery Engine의 source_discovery 단계(지시서 28-4/28-5) —
        구글 검색 그라운딩으로 공개 웹에서 실제 자료를 찾는다. 일반 generateContent와
        같은 엔드포인트를 쓰되 tools=[{"google_search": {}}]를 실어서, 모델이
        직접 검색을 수행하고 응답에 인용(citation) 목록을 함께 돌려주게 한다 —
        _ask_text와 달리 모델의 사전지식만으로 답하지 않는다.

        요청 자체가 실패하면(키 미설정/HTTP 실패/응답 구조가 예상과 다름)
        GroundingUnavailableError를 발생시켜 호출부가 그 사유를 알 수 있게 한다.
        요청이 정상 응답했지만 인용이 하나도 없는 경우는 예외가 아니라
        citations=[]인 정상 GroundingResult로 돌려준다 — "요청이 실패했다"와
        "실제로 자료가 없었다"는 서로 다른 사실이라 섞지 않는다(호출부인
        source_discovery.discover_sources가 citations 빈 값을 "자료 없음"으로
        해석)."""
        if not self._key:
            logger.warning("ground_search: GEMINI_API_KEY 미설정")
            raise GroundingUnavailableError("NO_API_KEY")

        payload = {
            "contents": [{"parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                data = await self._post_generate_content(client, payload)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                detail = _extract_error_detail(exc.response)
                logger.warning(
                    "ground_search HTTP 실패: status=%s detail=%s query=%r", status, detail, query
                )
                raise GroundingUnavailableError(f"HTTP_{status}", detail=detail) from exc
            except httpx.HTTPError as exc:
                logger.warning(
                    "ground_search 요청 실패: %s query=%r", exc.__class__.__name__, query
                )
                raise GroundingUnavailableError(exc.__class__.__name__[:20]) from exc

        try:
            candidate = data["candidates"][0]
            text = candidate["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            logger.warning("ground_search 응답 구조 이상: keys=%s", list(data.keys()))
            raise GroundingUnavailableError("BAD_RESPONSE_SHAPE")

        citations: list[GroundingCitation] = []
        grounding_chunks = (candidate.get("groundingMetadata") or {}).get("groundingChunks") or []
        for chunk in grounding_chunks:
            web = chunk.get("web") or {}
            url = web.get("uri")
            if not url:
                continue
            citations.append(GroundingCitation(url=url, title=web.get("title") or url))

        if not citations:
            logger.info("ground_search: 응답은 정상이나 인용 없음 query=%r", query)

        return GroundingResult(text=text, citations=citations)

    async def extract_from_image(self, image_url: str) -> OcrResult:
        raw_text = await self._ask_about_image(image_url, _EXTRACTION_PROMPT)

        try:
            parsed = json.loads(_strip_code_fence(raw_text))
        except (json.JSONDecodeError, IndexError):
            return OcrResult(raw_text=raw_text, price=None, title=None, category=None)

        category_value = parsed.get("category")
        category = Category(category_value) if category_value in _VALID_CATEGORIES else None

        return OcrResult(
            raw_text=raw_text,
            price=parsed.get("price"),
            title=parsed.get("title"),
            category=category,
            location_text=parsed.get("location_text"),
        )

    async def estimate_typical_price(self, item_name: str) -> float | None:
        """메뉴의 통상 시세를 추정한다 — 주변에 같은 메뉴를 등록한 매장이 아직 없어도
        절약 정보를 계산할 수 있게 하는 콜드스타트 보조값. 실측 비교가 가능해지면
        그쪽이 항상 우선하며, 사용자에게는 항상 "AI 추정"으로 표시한다.
        추정이 불가능하거나 API 호출이 실패하면 None (지어내지 않고 비워둔다)."""
        try:
            raw_text = await self._ask_text(_typical_price_prompt(item_name))
        except (OcrServiceError, ReportImageFetchError):
            return None

        try:
            parsed = json.loads(_strip_code_fence(raw_text))
        except (json.JSONDecodeError, IndexError):
            return None

        price = parsed.get("typical_price") if isinstance(parsed, dict) else None
        if not isinstance(price, (int, float)) or price <= 0:
            return None
        return float(price)

    async def summarize_route(
        self,
        stops: list[dict],
        budget: float,
        party_size: int,
        total_spend: float,
        total_savings: float,
        context_note: str | None = None,
    ) -> str | None:
        """이미 계산 끝난 절약 코스(장소/가격/절약률)를 자연어 한 문단으로 phrase만
        한다 — 프롬프트에도 명시하지만, 숫자·장소 자체는 절대 여기서 새로 만들지
        않는다(호출부가 이미 결정론적으로 계산해서 넘긴다). estimate_typical_price와
        동일하게 실패 시 예외를 밖으로 던지지 않고 None으로 fail-soft — 호출부
        (route_planner.generate_summary)가 결정론적 템플릿 문장으로 대체한다.
        context_note는 사용자가 고른 활동/조건 요약(설명 근거용, 숫자 계산에는 안 씀)."""
        try:
            raw_text = await self._ask_text(
                _route_summary_prompt(
                    stops, budget, party_size, total_spend, total_savings, context_note
                )
            )
        except (OcrServiceError, ReportImageFetchError):
            return None
        text = raw_text.strip()
        return text or None

    async def generate_offer_blurb(self, facts: dict[str, str]) -> str | None:
        """AI 활용 확대 안건 D(2026-08-31) — 매장 카드 한 줄 소개를 실제 사실(facts)만
        근거로 자연스럽게 phrase한다. summarize_route와 완전히 같은 원칙(AI는 문장
        표현만, 숫자/사실은 호출부가 이미 결정한 것만 씀)과 같은 fail-soft 계약 —
        실패하면 예외를 던지지 않고 None (호출부인 offer_blurb_backfill이 이번엔
        건너뛰고 다음 배치 실행 때 다시 시도하거나, 계속 결정론적 템플릿을 쓰게 한다)."""
        try:
            raw_text = await self._ask_text(_offer_blurb_prompt(facts))
        except (OcrServiceError, ReportImageFetchError):
            return None
        text = raw_text.strip()
        return text or None

    async def extract_menu_items(self, image_url: str) -> list[MenuItemGuess]:
        """메뉴판 사진에서 메뉴명·가격 목록을 통째로 추출한다 (사장님이 하나씩
        타이핑하지 않아도 되도록). 결과는 저장 전 사용자 확인을 거친다."""
        raw_text = await self._ask_about_image(image_url, _MENU_EXTRACTION_PROMPT)

        try:
            parsed = json.loads(_strip_array_fence(raw_text))
        except (json.JSONDecodeError, IndexError):
            return []

        if not isinstance(parsed, list):
            return []

        guesses: list[MenuItemGuess] = []
        for row in parsed:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            price = row.get("price")
            if not name or not isinstance(price, (int, float)):
                continue
            guesses.append(MenuItemGuess(name=str(name).strip(), price=float(price)))
        return guesses

    async def extract_price_discovery(
        self,
        store_name: str,
        store_address: str | None,
        store_category: str | None,
        grounded_text: str,
        citations: list[GroundingCitation],
    ) -> PriceDiscoveryExtraction | None:
        """AI Price Discovery Engine의 price_extractor 단계(지시서 28-6) —
        ground_search가 찾은 텍스트+인용을 지정된 JSON 스키마로 구조화한다.
        _ask_text를 그대로 재사용하고(새 HTTP 경로 안 만듦), 파싱/검증에 실패하면
        전부 None을 돌려준다 — 스키마가 안 맞는 응답을 억지로 해석해서 가격을
        만들어내지 않는다(28-29 "AI 출력은 절대 DB에 직접 저장하지 않는다"의
        첫 관문)."""
        prompt = _price_discovery_extraction_prompt(
            store_name, store_address, store_category, grounded_text, citations
        )
        try:
            raw_text = await self._ask_text(prompt)
        except (OcrServiceError, ReportImageFetchError):
            return None

        try:
            parsed = json.loads(_strip_code_fence(raw_text))
        except (json.JSONDecodeError, IndexError):
            return None
        if not isinstance(parsed, dict):
            return None

        match_raw = parsed.get("store_match")
        if not isinstance(match_raw, dict):
            return None
        confidence = match_raw.get("confidence")
        if not isinstance(confidence, (int, float)):
            return None
        store_match = PriceDiscoveryStoreMatch(
            matched=bool(match_raw.get("matched")),
            confidence=max(0.0, min(float(confidence), 1.0)),
            reason=str(match_raw.get("reason") or ""),
        )

        cited_urls = {c.url for c in citations}
        prices: list[PriceDiscoveryPriceItem] = []
        for row in parsed.get("prices") or []:
            if not isinstance(row, dict):
                continue
            name = row.get("menu_name")
            price = row.get("price")
            source_type = row.get("source_type")
            source_url = row.get("source_url")
            # 규칙 8 "출처 URL을 반드시 반환한다" + 규칙 1 "자료에 명시된 가격만" —
            # 이 그라운딩 호출에서 실제로 인용된 URL이 아니면(모델이 지어냈거나
            # 다른 자료를 섞었을 가능성) 그 항목은 버린다.
            if (
                not name
                or not isinstance(price, (int, float))
                or price <= 0
                or source_type not in ("official", "web")
                or source_url not in cited_urls
            ):
                continue
            prices.append(
                PriceDiscoveryPriceItem(
                    menu_name=str(name).strip(),
                    price=float(price),
                    source_type=source_type,
                    source_url=source_url,
                    source_title=(str(row["source_title"]) if row.get("source_title") else None),
                    observed_at=(str(row["observed_at"]) if row.get("observed_at") else None),
                    evidence=(str(row["evidence"])[:500] if row.get("evidence") else None),
                )
            )

        return PriceDiscoveryExtraction(store_match=store_match, prices=prices)

    async def review_price_update(
        self, item_name: str, image_url: str, old_price: float, old_verified_at: str, new_price: float
    ) -> tuple[bool, str]:
        """이미 등록된 메뉴 가격과 다른 값이 다시 제보되면 AI가 새 사진 + 기존
        가격의 최신성을 보고 갱신 여부를 판단한다(사용자 지시, 2026-08-18: "가격이
        다를경우 사진에 정보 시간 및 일자, 최신성을 반영해서 검토해 AI로"). 사진을
        다시 확인 못 하거나 응답을 이해 못 하면 보수적으로 거부(기존 값 유지) —
        검증 안 된 가격으로 함부로 덮어쓰지 않는다."""
        try:
            raw_text = await self._ask_about_image(
                image_url,
                _price_update_review_prompt(item_name, old_price, old_verified_at, new_price),
            )
        except (OcrServiceError, ReportImageFetchError):
            return False, "사진을 다시 확인하지 못해 기존 가격을 유지했어요"

        try:
            parsed = json.loads(_strip_code_fence(raw_text))
        except (json.JSONDecodeError, IndexError):
            return False, "AI가 사진을 판단하지 못해 기존 가격을 유지했어요"

        if not isinstance(parsed, dict):
            return False, "AI가 사진을 판단하지 못해 기존 가격을 유지했어요"

        accept = bool(parsed.get("accept_update"))
        reason = parsed.get("reason")
        default_reason = "가격 갱신을 확인했어요" if accept else "가격 갱신을 확인하지 못해 기존 가격을 유지했어요"
        return accept, (str(reason) if reason else default_reason)
