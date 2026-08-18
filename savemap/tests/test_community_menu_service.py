import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

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


# --- submit_menu_report_batch (2026-08-18 재설계) --- 예전엔 "매장당 최초
# 1회(배치 전체)만 허용"으로 이후 등록을 전부 막았지만, 사업자 등록을 비활성화하고
# 사용자 메뉴 제보를 유일한 등록/갱신 경로로 삼으면서(사용자 지시: "사장님 등록은
# 일단 비활성화 시키고 사용자가 메뉴 등록하는걸로 구조를 바꿔") 항목 단위로
# created/unchanged/updated/rejected를 판정하는 구조로 바뀌었다. 아래는 그 네 갈래
# 분기와, 사진 없이는 가격 갱신을 절대 받아들이지 않는다는 걸 검증한다.
class _FakePlace:
    def __init__(self, place_id=1):
        self.id = place_id


class _FakeExistingMenuItem:
    """이미 DB에 저장돼 있다고 가정하는 기존 MenuItem을 흉내낸다 — session.add를
    거치지 않으므로 id가 생성 시점부터 고정돼 있다(실제 ORM에서 조회해 온 행과 같음)."""

    def __init__(self, id, place_id, name, price, source_url=None, verified_at=None):
        self.id = id
        self.place_id = place_id
        self.name = name
        self.price = price
        self.source_url = source_url
        self.verified_at = verified_at


class _FakeBatchSession:
    """lookup_results는 submit_menu_report_batch가 항목을 처리하는 순서대로
    select(MenuItem).where(...)의 결과를 미리 정해준다 — 실제 SQL where 절을
    파싱하지 않고, 항목별 시나리오(신규/기존)를 테스트가 직접 통제한다."""

    def __init__(self, lookup_results: list[object | None]):
        self._lookup_results = list(lookup_results)
        self._call_index = 0
        self.added = []
        self._next_id = 100

    async def execute(self, *a, **kw):
        value = self._lookup_results[self._call_index]
        self._call_index += 1
        return _FakeResult(value)

    def add(self, obj):
        obj.id = self._next_id
        self._next_id += 1
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _patch_report_dependencies(xp_per_item=5, review_result=None):
    """award_xp/sync_menu_offer/GeminiVisionClient.estimate_typical_price/
    review_price_update는 이 함수 바깥의 관심사(XP 원장, 오퍼 동기화, AI 판단)라
    얇게 스텁만 한다. review_result가 주어지면 (accept, reason) 튜플을 그대로
    review_price_update의 반환값으로 쓴다."""
    patches = [
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
    ]
    if review_result is not None:
        patches.append(
            patch(
                "app.integrations.gemini.GeminiVisionClient.review_price_update",
                new=AsyncMock(return_value=review_result),
            )
        )
    return patches


def test_submit_menu_report_batch_creates_new_item_when_no_existing_menu_item():
    session = _FakeBatchSession(lookup_results=[None])
    place = _FakePlace()
    with patch("app.sources.community_menu.service.award_xp", new=AsyncMock(return_value=5)), patch(
        "app.sources.community_menu.service.sync_menu_offer", new=AsyncMock(return_value="fake-comparison")
    ), patch("app.integrations.gemini.GeminiVisionClient.estimate_typical_price", new=AsyncMock(return_value=None)):
        results = asyncio.run(
            submit_menu_report_batch(session, "user-1", place, [("아메리카노", 4500.0, None)])
        )
    assert len(results) == 1
    item, cmp, xp, status, review_note = results[0]
    assert item.name == "아메리카노"
    assert status == "created"
    assert review_note is None
    assert xp == 5
    assert cmp == "fake-comparison"
    assert len(session.added) == 1


def test_submit_menu_report_batch_skips_when_price_unchanged():
    # 가격이 사실상 같으면(오차 허용치 이내) AI를 태우지 않고 그대로 둔다 — 중복
    # 제보로 XP를 파밍하거나 매번 AI 호출 비용을 쓰는 걸 막기 위함.
    existing = _FakeExistingMenuItem(id=7, place_id=1, name="아메리카노", price=4500.0)
    session = _FakeBatchSession(lookup_results=[existing])
    place = _FakePlace()
    with patch("app.sources.community_menu.service.sync_menu_offer", new=AsyncMock(return_value="fake-comparison")):
        results = asyncio.run(
            submit_menu_report_batch(session, "user-1", place, [("아메리카노", 4500.4, None)])
        )
    assert len(results) == 1
    item, cmp, xp, status, review_note = results[0]
    assert item is existing
    assert status == "unchanged"
    assert xp == 0
    assert review_note is None
    assert cmp == "fake-comparison"
    assert session.added == []  # 새로 저장한 게 없어야 한다


def test_submit_menu_report_batch_updates_when_price_differs_and_ai_accepts():
    existing = _FakeExistingMenuItem(
        id=7,
        place_id=1,
        name="아메리카노",
        price=4500.0,
        source_url="https://old.jpg",
        verified_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    session = _FakeBatchSession(lookup_results=[existing])
    place = _FakePlace()
    patches = _patch_report_dependencies(
        xp_per_item=5, review_result=(True, "새 사진에서 5000원이 명확히 보임")
    )
    with patches[0], patches[1], patches[2], patches[3] as mock_review:
        results = asyncio.run(
            submit_menu_report_batch(session, "user-1", place, [("아메리카노", 5000.0, "https://new.jpg")])
        )
    assert mock_review.await_count == 1
    item, cmp, xp, status, review_note = results[0]
    assert item is existing
    assert item.price == 5000.0
    assert item.source_url == "https://new.jpg"
    assert status == "updated"
    assert review_note == "새 사진에서 5000원이 명확히 보임"
    assert xp == 5
    assert cmp == "fake-comparison"


def test_submit_menu_report_batch_rejects_when_price_differs_and_ai_rejects():
    existing = _FakeExistingMenuItem(
        id=7, place_id=1, name="아메리카노", price=4500.0, source_url="https://old.jpg"
    )
    session = _FakeBatchSession(lookup_results=[existing])
    place = _FakePlace()
    patches = _patch_report_dependencies(review_result=(False, "사진이 흐릿해서 확인 불가"))
    with patches[0], patches[1], patches[2], patches[3]:
        results = asyncio.run(
            submit_menu_report_batch(session, "user-1", place, [("아메리카노", 3000.0, "https://blurry.jpg")])
        )
    item, cmp, xp, status, review_note = results[0]
    assert item is existing
    assert item.price == 4500.0  # 거부됐으니 기존 가격 그대로
    assert cmp is None
    assert xp == 0
    assert status == "rejected"
    assert review_note == "사진이 흐릿해서 확인 불가"
    assert session.added == []


def test_submit_menu_report_batch_rejects_without_photo_and_skips_ai_call():
    # 새 가격을 검증할 사진이 없으면 AI 호출조차 하지 않고 바로 거부한다 — 근거
    # 없는 숫자로 덮어쓰지 않는다는 원칙.
    existing = _FakeExistingMenuItem(id=7, place_id=1, name="아메리카노", price=4500.0)
    session = _FakeBatchSession(lookup_results=[existing])
    place = _FakePlace()
    with patch(
        "app.integrations.gemini.GeminiVisionClient.review_price_update", new=AsyncMock()
    ) as mock_review:
        results = asyncio.run(
            submit_menu_report_batch(session, "user-1", place, [("아메리카노", 3000.0, None)])
        )
    mock_review.assert_not_awaited()
    item, cmp, _xp, status, _review_note = results[0]
    assert status == "rejected"
    assert cmp is None
    assert item.price == 4500.0


def test_submit_menu_report_batch_saves_all_items_in_one_batch_when_place_is_new():
    # 사진 한 장에서 메뉴 여러 개가 인식되는 정상 케이스 — 각 항목이 서로 독립적으로
    # 처리돼야 한다(다른 항목이 이미 있다고 해서 새 항목까지 막히면 안 됨).
    session = _FakeBatchSession(lookup_results=[None, None, None])
    place = _FakePlace()
    with patch("app.sources.community_menu.service.award_xp", new=AsyncMock(return_value=5)), patch(
        "app.sources.community_menu.service.sync_menu_offer", new=AsyncMock(return_value="fake-comparison")
    ), patch("app.integrations.gemini.GeminiVisionClient.estimate_typical_price", new=AsyncMock(return_value=None)):
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
    assert [item.name for item, _cmp, _xp, _status, _note in results] == ["아메리카노", "라떼", "아이스티"]
    assert all(status == "created" for _item, _cmp, _xp, status, _note in results)
    assert all(xp == 5 for _item, _cmp, xp, _status, _note in results)
