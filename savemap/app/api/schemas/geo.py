from pydantic import BaseModel


class ReverseGeocodeResponse(BaseModel):
    region: str | None = None


class GeocodeSearchResponse(BaseModel):
    """주소 순방향 검색(1번 항목) 결과 — 못 찾으면 found=False, 나머지 필드는 None."""

    found: bool
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
