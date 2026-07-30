import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.engine.discovery import discover_nearby_places
from app.integrations.kakao import KakaoPlace


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
