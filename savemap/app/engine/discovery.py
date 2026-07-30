from dataclasses import dataclass

from app.core.spatial import haversine_m
from app.integrations.kakao import KakaoClient, KakaoPlace

RESTAURANT_CAFE_CATEGORY_CODES = ("FD6", "CE7")  # 음식점, 카페
DEDUPE_DISTANCE_M = 30.0
MAX_DISCOVERED = 20


@dataclass
class DiscoveredCandidate:
    place: KakaoPlace
    distance_m: float


async def discover_nearby_places(
    lat: float,
    lng: float,
    radius_km: float,
    existing_coords: list[tuple[float, float]],
    kakao: KakaoClient | None = None,
) -> list[DiscoveredCandidate]:
    """SaveMap에 아직 가격/절약 정보가 등록되지 않은 주변 음식점·카페를 카카오 로컬
    API로 찾는다. 콜드스타트 문제(초기에 아무도 매장을 등록하지 않아 지도가 텅 비는 것)
    완화용 — 가격 비교는 못 보여줘도 "여기 이런 매장이 있다"는 발견은 항상 가능하게 한다."""
    client = kakao or KakaoClient()
    radius_m = int(radius_km * 1000)

    raw: list[KakaoPlace] = []
    for code in RESTAURANT_CAFE_CATEGORY_CODES:
        try:
            raw.extend(await client.search_category(lat, lng, radius_m, code))
        except Exception:
            continue  # 카카오 API가 실패해도 기존(가격 있는) 검색 결과는 그대로 반환돼야 한다

    seen: set[str] = set()
    candidates: list[DiscoveredCandidate] = []
    for p in raw:
        if p.kakao_place_id in seen:
            continue
        seen.add(p.kakao_place_id)
        if any(
            haversine_m(p.lat, p.lng, elat, elng) < DEDUPE_DISTANCE_M for elat, elng in existing_coords
        ):
            continue  # 이미 가격 정보가 있는(=results에 포함된) 매장과 같은 곳이면 중복 표시 안 함
        candidates.append(DiscoveredCandidate(place=p, distance_m=haversine_m(lat, lng, p.lat, p.lng)))

    candidates.sort(key=lambda c: c.distance_m)
    return candidates[:MAX_DISCOVERED]
