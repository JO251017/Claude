import asyncio

from app.sources.community_menu.service import find_or_create_place


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
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
