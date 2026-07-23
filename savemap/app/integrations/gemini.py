from dataclasses import dataclass

from app.core.config import settings
from app.domain.enums import Category


@dataclass
class OcrResult:
    raw_text: str
    price: float | None
    title: str | None
    category: Category | None


class GeminiVisionClient:
    def __init__(self, api_key: str | None = None):
        self._key = api_key or settings.gemini_api_key

    async def extract_from_image(self, image_url: str) -> OcrResult:
        if not self._key:
            raise RuntimeError("GEMINI_API_KEY 미설정")
        raise NotImplementedError("Gemini 1.5 Flash Vision 프롬프트/스키마 확정 후 구현")
