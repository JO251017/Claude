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

    async def directions(self, origin: tuple[float, float], dest: tuple[float, float]) -> dict:
        raise NotImplementedError("카카오모빌리티 길찾기 스펙 확인 후 구현 (미확인)")
