"""AI Price Discovery Engine — source_discovery 단계(지시서 28-4/28-5).

사용자가 선택한 방식(Gemini 검색 그라운딩)으로 매장 메뉴/가격을 다루는 공개
자료를 찾는다. 실제 HTTP 호출과 인용 파싱은 app/integrations/gemini.py의
GeminiVisionClient.ground_search가 담당하고, 이 모듈은 쿼리 문구 구성과 "자료를
못 찾았다"의 판정만 맡는다."""

from app.domain.place import Place
from app.integrations.gemini import GeminiVisionClient, GroundingResult


def _search_query(place: Place) -> str:
    parts = [place.name]
    if place.address:
        parts.append(place.address)
    parts.append("메뉴 가격")
    return " ".join(parts)


async def discover_sources(
    place: Place, client: GeminiVisionClient | None = None
) -> GroundingResult | None:
    """공개 자료를 못 찾았으면(citations가 비어있음) None — 가격을 못 찾았다는
    뜻으로 다음 단계(추출)로 넘기지 않는다(핵심 원칙: AI가 가격을 만들어내지
    않는다).

    ground_search 요청 자체가 실패한 경우(GroundingUnavailableError — 키
    미설정/HTTP 실패/응답 구조 이상)는 여기서 삼키지 않고 그대로 호출부로
    전파한다 — orchestrator가 그 사유를 error_code로 남겨서, "정말 자료가
    없는 매장"과 "요청이 매번 실패하는 설정/네트워크 문제"를 관리자 페이지에서
    구분할 수 있게 한다(실사용 중 둘이 똑같이 NO_SOURCE_FOUND로만 보여서
    구분이 안 됐던 문제, 2026-08-31)."""
    client = client or GeminiVisionClient()
    result = await client.ground_search(_search_query(place))
    if not result.citations:
        return None
    return result
