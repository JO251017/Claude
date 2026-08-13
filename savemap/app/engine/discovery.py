import time
from dataclasses import dataclass

from app.core.spatial import haversine_m
from app.integrations.kakao import KakaoClient, KakaoPlace

RESTAURANT_CAFE_CATEGORY_CODES = ("FD6", "CE7")  # 음식점, 카페
# 쇼핑(마트/편의점) 발견 확장 — "SaveMap 구조 재설계 제안서"(2026-08-13) §6:
# Activity 후보 중 확장 비용이 가장 낮다고 판단한 항목. search_category()가 이미
# category_group_code를 파라미터로 받는 범용 함수라 코드만 추가하면 된다. 단,
# 이건 "발견"(가격 없는 상태로 지도에 보여주기)까지만이다 — 실제 가격/Offer
# 데이터가 없는 한 AI 절약 플랜의 RouteActivity로는 아직 못 넣는다(활동 분류가
# 아니라 발견 범위 확장).
SHOPPING_CATEGORY_CODES = ("MT1", "CS2")  # 대형마트, 편의점
DISCOVERY_CATEGORY_CODES = RESTAURANT_CAFE_CATEGORY_CODES + SHOPPING_CATEGORY_CODES
DEDUPE_DISTANCE_M = 30.0
MAX_DISCOVERED = 20

# 같은(또는 근처) 위치를 여러 번 검색해도(사용자가 지도를 조금씩 움직이거나, 같은
# 반경을 새로고침하는 경우) 카카오 API를 매번 실시간으로 다시 호출하고 있었다 —
# 이 API 자체가 매 /search 요청마다 카테고리 2개씩 불려서, 검색이 잦아지면 그만큼
# 레이턴시와 쿼터를 계속 갚아나가는 구조였다(2026-08-12). 어차피 이 결과는
# "아직 가격 정보가 없는 매장 발견"용이라 몇 분 정도 오래돼도 문제 없으니, 좌표를
# ~100m 격자로 반올림해 짧게 캐시해서 반복 호출을 줄인다.
_CACHE_TTL_SEC = 300
_CACHE_MAX = 500
_kakao_cache: dict[tuple, dict] = {}


def _cache_key(lat: float, lng: float, radius_m: int, code: str) -> tuple:
    return (round(lat, 3), round(lng, 3), radius_m, code)


def _prune_kakao_cache() -> None:
    now = time.time()
    for key in [k for k, v in _kakao_cache.items() if now - v["at"] > _CACHE_TTL_SEC]:
        del _kakao_cache[key]
    while len(_kakao_cache) > _CACHE_MAX:
        oldest_key = min(_kakao_cache, key=lambda k: _kakao_cache[k]["at"])
        del _kakao_cache[oldest_key]


async def _search_category_cached(
    client: KakaoClient, lat: float, lng: float, radius_m: int, code: str
) -> list[KakaoPlace]:
    key = _cache_key(lat, lng, radius_m, code)
    cached = _kakao_cache.get(key)
    now = time.time()
    if cached is not None and now - cached["at"] < _CACHE_TTL_SEC:
        return cached["places"]
    places = await client.search_category(lat, lng, radius_m, code)
    _kakao_cache[key] = {"places": places, "at": now}
    _prune_kakao_cache()
    return places


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
    """SaveMap에 아직 가격/절약 정보가 등록되지 않은 주변 음식점·카페·마트·편의점을
    카카오 로컬 API로 찾는다. 콜드스타트 문제(초기에 아무도 매장을 등록하지 않아 지도가
    텅 비는 것) 완화용 — 가격 비교는 못 보여줘도 "여기 이런 매장이 있다"는 발견은 항상
    가능하게 한다."""
    client = kakao or KakaoClient()
    radius_m = int(radius_km * 1000)

    raw: list[KakaoPlace] = []
    for code in DISCOVERY_CATEGORY_CODES:
        try:
            raw.extend(await _search_category_cached(client, lat, lng, radius_m, code))
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
