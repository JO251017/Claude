import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.errors import PlaceMenuAlreadyRegisteredError
from app.sources.community_menu.service import find_or_create_place, submit_menu_report_batch


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class _FakeSession:
    """execute/get/add/commit/refresh만 흉내 낸다. get_store는 place_id -> Place."""

    def __init__(self, get_store: dict[int, object] | None = None, kakao_match=None):
        self.get_store = get_store or {}
        self.kakao_match = kakao_match  # kakao_place_id 조회 시 돌려줄 Place (없으면 None)
        self.added = []
        self.executed_where_kakao = False

    async def get(self, model, pk):
        return self.get_store.get(pk)

    async def execute(self, *a, **kw):
        # find_or_create_place가 kakao_place_id로만 조회한다 — 이 fake는 그 호출이
        # 실제로 일어났는지와, 준비된 kakao_match를 그대로 돌려주는지만 확인하면 된다.
        self.executed_where_kakao = True
        return _FakeResult(self.kakao_match)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def test_place_id_priority_skips_kakao_lookup_entirely():
    # 인허가 데이터로 이미 DB에 있는 Place(kakao_place_id=None)를 place_id로 바로 찾는
    # 경우 — kakao_place_id=None으로 조회했다간(수천 건이 NULL이라) MultipleResultsFound가
    # 나므로, place_id가 있으면 kakao 조회 자체를 하면 안 된다.
    existing_place = object()
    session = _FakeSession(get_store={42: existing_place})

    result = asyncio.run(
        find_or_create_place(
            session,
            place_id=42,
            kakao_place_id=None,
            name="가게",
            address="주소",
            phone=None,
            lat=36.99,
            lng=127.11,
        )
    )
    assert result is existing_place
    assert session.executed_where_kakao is False, "place_id로 찾았으면 kakao_place_id 조회를 하면 안 된다"
    assert session.added == []


def test_falls_back_to_kakao_place_id_when_no_place_id():
    existing_place = object()
    session = _FakeSession(kakao_match=existing_place)

    result = asyncio.run(
        find_or_create_place(
            session,
            place_id=None,
            kakao_place_id="kakao-123",
            name="가게",
            address="주소",
            phone=None,
            lat=36.99,
            lng=127.11,
        )
    )
    assert result is existing_place
    assert session.executed_where_kakao is True
    assert session.added == []


def test_creates_new_place_without_touching_null_kakao_lookup():
    # place_id도 kakao_place_id도 없으면(완전히 새로 발견된 곳) kakao_place_id=None으로
    # 조회하지 않고 바로 새 Place를 만들어야 한다 — None으로 조회하면 registry 데이터로
    # kakao_place_id가 비어있는 다른 Place들과 걸려 MultipleResultsFound가 날 수 있다.
    session = _FakeSession()

    result = asyncio.run(
        find_or_create_place(
            session,
            place_id=None,
            kakao_place_id=None,
            name="새로운 가게",
            address="주소",
            phone=None,
            lat=36.99,
            lng=127.11,
        )
    )
    assert session.executed_where_kakao is False
    assert len(session.added) == 1
    assert session.added[0] is result
    assert result.kakao_place_id is None


# --- submit_menu_report_batch (2026-08-13) --- 오픈 커뮤니티 메뉴 제보 경로를
# "매장당 최초 1회(배치 전체)만 허용"으로 막는 안전장치와, 그 판정이 같은 배치
# 안의 여러 항목끼리는 서로 막지 않는지를 확인한다.
class _FakePlace:
    def __init__(self, place_id=1):
        self.id = place_id


class _FakeMenuItem:
    """session.add(MenuItem(...))로 넘어온 객체가 그대로 refresh 후 id를 갖도록
    흉내낸다 — 실제 ORM처럼 자동증가 PK를 시뮬레이션."""

    _next_id = 100

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = None


class _FakeBatchSession:
    def __init__(self, existing_menu_item_count: int):
        self._count = existing_menu_item_count
        self.added = []
        self._next_id = 100

    async def execute(self, *a, **kw):
        return _FakeResult(self._count)

    def add(self, obj):
        obj.id = self._next_id
        self._next_id += 1
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _patch_report_dependencies(xp_per_item=5):
    """award_xp/sync_menu_offer/GeminiVisionClient.estimate_typical_price는 이
    함수 바깥의 관심사(XP 원장, 오퍼 동기화, AI 통상가 추정)라 얇게 스텁만 한다."""
    return (
        patch(
            "app.sources.community_menu.service.award_xp",
            new=AsyncMock(return_value=xp_per_item),
        ),
        patch(
            "app.sources.community_menu.service.sync_menu_offer",
            new=AsyncMock(return_value="fake-comparison"),
        ),
        patch(
            "app.integrations.gemini.GeminiVisionClient.estimate_typical_price",
            new=AsyncMock(return_value=None),
        ),
    )


def test_submit_menu_report_batch_rejects_when_place_already_has_menu_items():
    session = _FakeBatchSession(existing_menu_item_count=1)
    place = _FakePlace()
    p1, p2, p3 = _patch_report_dependencies()
    with p1, p2, p3:
        with pytest.raises(PlaceMenuAlreadyRegisteredError):
            asyncio.run(
                submit_menu_report_batch(session, "user-1", place, [("아메리카노", 4500.0, None)])
            )
    assert session.added == []  # 거부됐으면 아무것도 저장하면 안 된다


def test_submit_menu_report_batch_saves_all_items_in_one_batch_when_place_is_new():
    # 사진 한 장에서 메뉴 여러 개가 인식되는 정상 케이스 — "이미 등록됨" 판정이
    # 배치 시작 전 한 번만 이뤄져서, 두 번째/세 번째 항목이 스스로를 막으면 안 된다.
    session = _FakeBatchSession(existing_menu_item_count=0)
    place = _FakePlace()
    p1, p2, p3 = _patch_report_dependencies(xp_per_item=5)
    with p1, p2, p3:
        results = asyncio.run(
            submit_menu_report_batch(
                session,
                "user-1",
                place,
                [("아메리카노", 4500.0, None), ("라떼", 5000.0, None), ("아이스티", 3500.0, None)],
            )
        )
    assert len(results) == 3
    assert len(session.added) == 3
    assert [item.name for item, _cmp, _xp in results] == ["아메리카노", "라떼", "아이스티"]
    assert all(xp == 5 for _item, _cmp, xp in results)
