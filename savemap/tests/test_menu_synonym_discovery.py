import asyncio
from unittest.mock import AsyncMock

from app.domain.menu_synonym import MenuSynonymCandidate
from app.engine.menu_synonym_discovery import discover_menu_synonym_candidates


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """첫 execute는 _load_candidate_names(그룹핑된 이름 목록), 두 번째는
    _load_existing_candidate_pairs(이미 저장된 후보 쌍) — 순서 고정이라 큐로
    흉내낸다."""

    def __init__(self, name_rows, existing_pairs=()):
        self._queue = [_Result(name_rows), _Result(list(existing_pairs))]
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        return self._queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _FakeClient:
    def __init__(self, pairs=(), raise_exc=None):
        self._pairs = list(pairs)
        self._raise_exc = raise_exc
        self.suggest_menu_synonyms_batch = AsyncMock(side_effect=self._call)

    async def _call(self, names):
        if self._raise_exc:
            raise self._raise_exc
        return list(self._pairs)


def test_saves_new_candidate_pairs():
    session = _FakeSession(name_rows=[("멘치가스", 500), ("멘치까스", 30)])
    client = _FakeClient(pairs=[("멘치까스", "멘치가스", "표기 차이")])
    result = asyncio.run(discover_menu_synonym_candidates(session, limit=300, client=client))

    assert result["found"] == 1
    assert result["saved"] == 1
    assert result["done"] is True
    assert session.commits == 1
    assert len(session.added) == 1
    saved = session.added[0]
    assert isinstance(saved, MenuSynonymCandidate)
    assert saved.variant == "멘치까스"
    assert saved.canonical == "멘치가스"
    assert saved.reason == "표기 차이"


def test_already_known_pair_is_not_saved_again():
    session = _FakeSession(
        name_rows=[("멘치가스", 500), ("멘치까스", 30)],
        existing_pairs=[("멘치까스", "멘치가스")],
    )
    client = _FakeClient(pairs=[("멘치까스", "멘치가스", "표기 차이")])
    result = asyncio.run(discover_menu_synonym_candidates(session, limit=300, client=client))

    assert result["found"] == 1
    assert result["saved"] == 0
    assert session.added == []


def test_self_pair_is_discarded():
    session = _FakeSession(name_rows=[("멘치가스", 500)])
    client = _FakeClient(pairs=[("멘치가스", "멘치가스", "같은 이름")])
    result = asyncio.run(discover_menu_synonym_candidates(session, limit=300, client=client))

    assert result["saved"] == 0
    assert session.added == []


def test_dry_run_does_not_commit_or_save():
    session = _FakeSession(name_rows=[("멘치가스", 500), ("멘치까스", 30)])
    client = _FakeClient(pairs=[("멘치까스", "멘치가스", "표기 차이")])
    result = asyncio.run(
        discover_menu_synonym_candidates(session, limit=300, dry_run=True, client=client)
    )

    assert result["dry_run"] is True
    assert session.added == []
    assert session.commits == 0
    assert session.rollbacks == 1


def test_batch_call_failure_does_not_crash_and_yields_zero():
    session = _FakeSession(name_rows=[("멘치가스", 500), ("멘치까스", 30)])
    client = _FakeClient(raise_exc=RuntimeError("boom"))
    result = asyncio.run(discover_menu_synonym_candidates(session, limit=300, client=client))

    assert result["found"] == 0
    assert result["saved"] == 0
    assert session.commits == 1  # 아무것도 없어도 정상적으로 커밋(빈 트랜잭션)까지 진행


def test_empty_candidate_list_marks_done_immediately():
    session = _FakeSession(name_rows=[])
    client = _FakeClient()
    result = asyncio.run(discover_menu_synonym_candidates(session, offset=0, limit=300, client=client))

    assert result["done"] is True
    assert result["scanned"] == 0
    client.suggest_menu_synonyms_batch.assert_not_awaited()


def test_pagination_offset_advances_by_page_size():
    """페이지네이션은 "메뉴명 개수" 기준이다 — 3개 이름에 limit=2면 첫 페이지는
    2개만 훑고 next_offset=2, done=False여야 한다."""
    session = _FakeSession(name_rows=[("a", 5), ("b", 4), ("c", 3)])
    client = _FakeClient(pairs=[])
    result = asyncio.run(discover_menu_synonym_candidates(session, offset=0, limit=2, client=client))

    assert result["scanned"] == 2
    assert result["next_offset"] == 2
    assert result["done"] is False
