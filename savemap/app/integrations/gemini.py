import base64
import json
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.errors import OcrServiceError, ReportImageFetchError
from app.domain.enums import Category

GEMINI_API_BASE = "https://generativelanguage.googleapis.com"
GEMINI_MODEL = "gemini-flash-latest"
MAX_IMAGE_BYTES = 10 * 1024 * 1024

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


class GeminiVisionClient:
    def __init__(self, api_key: str | None = None):
        self._key = api_key or settings.gemini_api_key

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
                resp = await client.post(
                    f"{GEMINI_API_BASE}/v1beta/models/{GEMINI_MODEL}:generateContent",
                    params={"key": self._key},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
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
                resp = await client.post(
                    f"{GEMINI_API_BASE}/v1beta/models/{GEMINI_MODEL}:generateContent",
                    params={"key": self._key},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                raise OcrServiceError(f"AI 요청에 실패했습니다: {exc.__class__.__name__}") from exc

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OcrServiceError("AI 응답을 이해할 수 없습니다") from exc

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
