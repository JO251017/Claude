import asyncio
from unittest.mock import AsyncMock

from sqlalchemy.exc import IntegrityError

from app.gamification.pet_reactions import _TEMPLATE_LEVELUP, get_or_create_levelup_message


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class _FakeSession:
    def __init__(self, existing=None, fail_commit=False, winner=None):
        self._existing = existing
        self._winner = winner
        self._fail_commit = fail_commit
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        # get_or_create_levelup_message가 부르는 순서: (1) 캐시 조회, (2, 실패
        # 레이스일 때만) 이긴 쪽 재조회.
        if self.commits == 0 and self.rollbacks == 0:
            return _FakeResult(self._existing)
        return _FakeResult(self._winner)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1
        if self._fail_commit:
            raise IntegrityError("dup", None, None)

    async def rollback(self):
        self.rollbacks += 1


class _FakeClient:
    def __init__(self, text="신난다!", raise_exc=None):
        self._text = text
        self._raise_exc = raise_exc
        self.generate_pet_levelup_line = AsyncMock(side_effect=self._call)

    async def _call(self, stage_name):
        if self._raise_exc:
            raise self._raise_exc
        return self._text


def test_returns_cached_message_without_calling_ai():
    from types import SimpleNamespace

    existing = SimpleNamespace(message="이미 있는 대사", source="ai")
    session = _FakeSession(existing=existing)
    client = _FakeClient()
    text, source = asyncio.run(
        get_or_create_levelup_message(session, 3, "산책 나온 강아지", client=client)
    )
    assert (text, source) == ("이미 있는 대사", "ai")
    client.generate_pet_levelup_line.assert_not_awaited()
    assert session.commits == 0


def test_generates_and_caches_ai_line():
    session = _FakeSession(existing=None)
    client = _FakeClient(text="신난다!")
    text, source = asyncio.run(get_or_create_levelup_message(session, 3, "산책 나온 강아지", client=client))
    assert (text, source) == ("신난다!", "ai")
    assert session.commits == 1
    assert session.added[0].stage_index == 3
    client.generate_pet_levelup_line.assert_awaited_once_with("산책 나온 강아지")


def test_falls_back_to_template_when_ai_returns_none():
    session = _FakeSession(existing=None)
    client = _FakeClient(text=None)
    text, source = asyncio.run(get_or_create_levelup_message(session, 3, "산책 나온 강아지", client=client))
    assert (text, source) == (_TEMPLATE_LEVELUP, "template")


def test_falls_back_to_template_when_ai_call_raises():
    session = _FakeSession(existing=None)
    client = _FakeClient(raise_exc=RuntimeError("boom"))
    text, source = asyncio.run(get_or_create_levelup_message(session, 3, "산책 나온 강아지", client=client))
    assert (text, source) == (_TEMPLATE_LEVELUP, "template")


def test_concurrent_race_returns_winner():
    from types import SimpleNamespace

    winner = SimpleNamespace(message="이긴 쪽 대사", source="ai")
    session = _FakeSession(existing=None, fail_commit=True, winner=winner)
    client = _FakeClient(text="신난다!")
    text, source = asyncio.run(get_or_create_levelup_message(session, 3, "산책 나온 강아지", client=client))
    assert (text, source) == ("이긴 쪽 대사", "ai")
    assert session.rollbacks == 1


def test_message_is_truncated_to_max_length():
    session = _FakeSession(existing=None)
    long_text = "가" * 100
    client = _FakeClient(text=long_text)
    text, source = asyncio.run(get_or_create_levelup_message(session, 3, "산책 나온 강아지", client=client))
    assert len(text) <= 40
    assert source == "ai"
