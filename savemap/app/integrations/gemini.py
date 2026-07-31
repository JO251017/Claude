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


_MENU_EXTRACTION_PROMPT = (
    "이 이미지는 식당/카페의 메뉴판 또는 메뉴 사진이야. 보이는 모든 메뉴 이름과 가격을 "
    "추출해줘. 가격을 알아볼 수 없는 항목은 제외해. "
    "반드시 아래 JSON 배열 형식으로만 응답하고 다른 텍스트는 포함하지 마:\n"
    '[{"name": "메뉴명", "price": 숫자}, ...]'
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
