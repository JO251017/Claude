import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine import discovery
from app.engine.discovery import discover_nearby_places
from app.integrations.kakao import KakaoPlace


@pytest.fixture(autouse=True)
def _clear_kakao_cache():
    # 이 파일의 테스트들이 같은 좌표(36.9925, 127.1130)를 재사용하는데, 캐시가
    # 테스트 간에도 그대로 남아있으면 한 테스트가 채운 캐시를 다음 테스트가
    # (mock을 호출하지 않고) 그대로 돌려받아 서로 오염된다 — 매 테스트 전에 비운다.
    discovery._kakao_cache.clear()
    yield
    discovery._kakao_cache.clear()


def _place(pid: str, name: str, lat: float, lng: float) -> KakaoPlace:
    return KakaoPlace(
        kakao_place_id=pid,
        name=name,
        address="경기 평택시",
        lat=lat,
        lng=lng,
        category_name="음식점 > 한식",
        place_url=f"https://place.map.kakao.com/{pid}",
    )


def test_discover_dedupes_and_filters_existing():
    kakao = MagicMock()
    kakao.search_category = AsyncMock(
        side_effect=[
            [_place("1", "새로운 식당", 36.9930, 127.1135), _place("2", "이미 있는 카페", 36.9925, 127.1130)],
            [_place("2", "이미 있는 카페", 36.9925, 127.1130)],  # 두 카테고리 호출 모두 중복 포함
        ]
    )

    result = asyncio.run(
        discover_nearby_places(
            36.9925, 127.1130, radius_km=3.0, existing_coords=[(36.9925, 127.1130)], kakao=kakao
        )
    )

    names = [c.place.name for c in result]
    assert "새로운 식당" in names
    assert "이미 있는 카페" not in names, "이미 SaveMap에 있는 매장(30m 이내)은 중복 표시하지 않아야 함"
    assert len(result) == 1, "같은 kakao_place_id가 두 카테고리에서 와도 한 번만 남아야 함"


def test_discover_returns_empty_when_kakao_fails():
    kakao = MagicMock()
    kakao.search_category = AsyncMock(side_effect=RuntimeError("API 실패"))

    result = asyncio.run(
        discover_nearby_places(36.9925, 127.1130, radius_km=3.0, existing_coords=[], kakao=kakao)
    )
    assert result == []


def test_repeated_search_at_same_spot_reuses_cache_instead_of_calling_kakao_again():
    # 같은 위치를 반복 검색해도(사용자가 새로고침 등) 카카오 API를 매번 다시 부르면
    # 안 된다 — 짧은 시간 안의 반복 호출은 캐시로 흡수돼야 한다(2026-08-12 개선).
    kakao = MagicMock()
    kakao.search_category = AsyncMock(
        return_value=[_place("1", "가게", 36.9930, 127.1135)]
    )

    asyncio.run(discover_nearby_places(36.9925, 127.1130, radius_km=3.0, existing_coords=[], kakao=kakao))
    call_count_after_first = kakao.search_category.await_count

    asyncio.run(discover_nearby_places(36.9925, 127.1130, radius_km=3.0, existing_coords=[], kakao=kakao))
    assert kakao.search_category.await_count == call_count_after_first, (
        "두 번째 호출은 캐시에서 응답해야 하고, 카카오 API를 다시 부르면 안 된다"
    )


def test_cache_expires_after_ttl(monkeypatch):
    kakao = MagicMock()
    kakao.search_category = AsyncMock(return_value=[_place("1", "가게", 36.9930, 127.1135)])

    asyncio.run(discover_nearby_places(36.9925, 127.1130, radius_km=3.0, existing_coords=[], kakao=kakao))
    call_count_after_first = kakao.search_category.await_count

    # TTL이 지난 것처럼 캐시 항목의 시각을 과거로 돌려서, 다음 호출이 다시 카카오를 불러야 함.
    for entry in discovery._kakao_cache.values():
        entry["at"] -= discovery._CACHE_TTL_SEC + 1

    asyncio.run(discover_nearby_places(36.9925, 127.1130, radius_km=3.0, existing_coords=[], kakao=kakao))
    assert kakao.search_category.await_count > call_count_after_first, "TTL이 지나면 다시 호출해야 한다"


def test_cache_evicts_oldest_entry_beyond_max_size(monkeypatch):
    import time

    monkeypatch.setattr(discovery, "_CACHE_MAX", 2)
    now = time.time()
    discovery._kakao_cache["a"] = {"places": [], "at": now - 3}
    discovery._kakao_cache["b"] = {"places": [], "at": now - 2}
    discovery._kakao_cache["c"] = {"places": [], "at": now - 1}

    discovery._prune_kakao_cache()

    assert len(discovery._kakao_cache) == 2
    assert "a" not in discovery._kakao_cache  # 가장 오래된 것부터 정리됨
    assert "c" in discovery._kakao_cache
