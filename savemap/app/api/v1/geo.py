from fastapi import APIRouter, Query

from app.api.schemas.geo import GeocodeSearchResponse, ReverseGeocodeResponse
from app.integrations.kakao import KakaoClient

router = APIRouter(tags=["geo"])


@router.get("/geo/reverse", response_model=ReverseGeocodeResponse)
async def reverse_geocode(
    lat: float = Query(...),
    lng: float = Query(...),
) -> ReverseGeocodeResponse:
    try:
        region = await KakaoClient().reverse_geocode(lat, lng)
    except Exception:
        # 위치명은 부가 정보라 카카오 API 실패로 홈 화면 전체를 막지 않는다.
        region = None
    return ReverseGeocodeResponse(region=region)


@router.get("/geo/search", response_model=GeocodeSearchResponse)
async def search_address(query: str = Query(..., min_length=1)) -> GeocodeSearchResponse:
    """주소/키워드 순방향 검색 (1번 항목) — MAP 상단 주소 검색창용.
    KakaoClient.geocode()는 이미 있었지만 HTTP로 노출된 적이 없었다."""
    try:
        result = await KakaoClient().geocode(query)
    except Exception:
        # 주소 검색 실패로 지도 화면 전체가 막히면 안 된다 — 못 찾음으로 취급.
        result = None
    if result is None:
        return GeocodeSearchResponse(found=False)
    return GeocodeSearchResponse(
        found=True, lat=result.lat, lng=result.lng, address=result.address
    )
