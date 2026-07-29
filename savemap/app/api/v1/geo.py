from fastapi import APIRouter, Query

from app.api.schemas.geo import ReverseGeocodeResponse
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
