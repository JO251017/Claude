"""AI Price Discovery Engine — price_extractor 단계(지시서 28-6/28-7).

source_discovery가 찾은 자료를 지정된 JSON 스키마로 구조화한다. 실제 프롬프트/
파싱/필드 검증은 app/integrations/gemini.py의 GeminiVisionClient.
extract_price_discovery가 담당한다(스키마 위반·근거 없는 URL 등은 거기서 이미
걸러짐). 이 모듈은 파이프라인 호출만 감싼다."""

from app.domain.place import Place
from app.integrations.gemini import GeminiVisionClient, GroundingResult, PriceDiscoveryExtraction


async def extract_prices(
    place: Place, grounding: GroundingResult, client: GeminiVisionClient | None = None
) -> PriceDiscoveryExtraction | None:
    client = client or GeminiVisionClient()
    return await client.extract_price_discovery(
        store_name=place.name,
        store_address=place.address,
        store_category=place.category_name,
        grounded_text=grounding.text,
        citations=grounding.citations,
    )
