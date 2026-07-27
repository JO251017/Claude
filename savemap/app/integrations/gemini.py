import base64
import json
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.domain.enums import Category

GEMINI_API_BASE = "https://generativelanguage.googleapis.com"
GEMINI_MODEL = "gemini-flash-latest"

_VALID_CATEGORIES = {c.value for c in Category}

_EXTRACTION_PROMPT = (
    "이 이미지(영수증, 전단지, 매장 사진 등)에서 절약 정보를 추출해줘. "
    "반드시 아래 JSON 형식으로만 응답하고 다른 텍스트는 포함하지 마:\n"
    '{"title": "혜택/상품명", "price": 숫자 또는 null, '
    f'"category": {sorted(_VALID_CATEGORIES)} 중 하나, '
    '"location_text": "이미지에서 보이는 가게 이름이나 주소가 있으면 그 텍스트, 없으면 null"}'
)


def _strip_code_fence(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


@dataclass
class OcrResult:
    raw_text: str
    price: float | None
    title: str | None
    category: Category | None
    location_text: str | None = None


class GeminiVisionClient:
    def __init__(self, api_key: str | None = None):
        self._key = api_key or settings.gemini_api_key

    async def extract_from_image(self, image_url: str) -> OcrResult:
        if not self._key:
            raise RuntimeError("GEMINI_API_KEY 미설정")

        async with httpx.AsyncClient(timeout=30) as client:
            img_resp = await client.get(image_url)
            img_resp.raise_for_status()
            image_bytes = img_resp.content
            mime_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0]

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": _EXTRACTION_PROMPT},
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
            resp = await client.post(
                f"{GEMINI_API_BASE}/v1beta/models/{GEMINI_MODEL}:generateContent",
                params={"key": self._key},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]

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
