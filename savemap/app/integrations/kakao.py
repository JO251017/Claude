from dataclasses import dataclass

import httpx

from app.core.config import settings

KAKAO_LOCAL_BASE = "https://dapi.kakao.com"


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    address: str
    kakao_place_id: str | None = None


@dataclass
class KakaoPlace:
    kakao_place_id: str
    name: str
    address: str | None
    lat: float
    lng: float
    category_name: str | None
    place_url: str | None


class KakaoClient:
    def __init__(self, api_key: str | None = None):
        self._key = api_key or settings.kakao_rest_api_key
        self._headers = {"Authorization": f"KakaoAK {self._key}"}

    async def geocode(self, query: str) -> GeocodeResult | None:
        if not self._key:
            raise RuntimeError("KAKAO_REST_API_KEY 미설정")
        async with httpx.AsyncClient(base_url=KAKAO_LOCAL_BASE, headers=self._headers) as client:
            resp = await client.get("/v2/local/search/address.json", params={"query": query})
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            if not docs:
                return None
            d = docs[0]
            return GeocodeResult(
                lat=float(d["y"]), lng=float(d["x"]), address=d.get("address_name", query)
            )

    async def reverse_geocode(self, lat: float, lng: float) -> str | None:
        """좌표 → 행정동/시군구 이름. 홈 화면 상단 "📍 OO시" 표시용."""
        if not self._key:
            return None
        async with httpx.AsyncClient(base_url=KAKAO_LOCAL_BASE, headers=self._headers) as client:
            resp = await client.get(
                "/v2/local/geo/coord2address.json", params={"x": lng, "y": lat}
            )
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            if not docs:
                return None
            region = docs[0].get("address") or {}
            parts = [
                region.get("region_1depth_name"),
                region.get("region_2depth_name"),
            ]
            return " ".join(p for p in parts if p) or None

    async def search_category(
        self, lat: float, lng: float, radius_m: int, category_group_code: str, page: int = 1
    ) -> list[KakaoPlace]:
        """카테고리로 장소 검색 (FD6=음식점, CE7=카페). SaveMap에 아직 가격 정보가 없는
        매장도 지도에서 발견은 되도록 하기 위한 콜드스타트용 — 아직 등록 안 한 매장을
        아예 못 찾는 문제를 막는다."""
        if not self._key:
            return []
        async with httpx.AsyncClient(base_url=KAKAO_LOCAL_BASE, headers=self._headers) as client:
            resp = await client.get(
                "/v2/local/search/category.json",
                params={
                    "category_group_code": category_group_code,
                    "x": lng,
                    "y": lat,
                    "radius": min(radius_m, 20000),
                    "page": page,
                    "size": 15,
                    "sort": "distance",
                },
            )
            resp.raise_for_status()
            docs = resp.json().get("documents", [])

        return [
            KakaoPlace(
                kakao_place_id=str(d["id"]),
                name=d.get("place_name", ""),
                address=d.get("road_address_name") or d.get("address_name"),
                lat=float(d["y"]),
                lng=float(d["x"]),
                category_name=d.get("category_name"),
                place_url=d.get("place_url"),
            )
            for d in docs
            if d.get("id") and d.get("place_name")
        ]

    async def directions(self, origin: tuple[float, float], dest: tuple[float, float]) -> dict:
        raise NotImplementedError("카카오모빌리티 길찾기 스펙 확인 후 구현 (미확인)")
