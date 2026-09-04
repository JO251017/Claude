"""사업자 콘솔 접근 제어(2-3, 2026-08-13) — merchant_verification 서비스 함수와
require_merchant_verified 의존성 자체를 FakeSession으로 얇게 검증한다. 실제 라우트
체인 검증(401/403)은 tests/test_api_routes.py 쪽에 있다."""

import asyncio

import pytest

from app.api.deps import require_merchant_verified
from app.core.errors import MerchantNotVerifiedError
from app.sources.merchant_console.service import (
    grant_merchant_verification,
    is_merchant_verified,
    revoke_merchant_verification,
)


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeExecuteSession:
    """execute()가 항상 같은 결과를 돌려주는 가장 단순한 형태 — 존재 여부(있음/없음)만
    확인하는 is_merchant_verified/require_merchant_verified 테스트용."""

    def __init__(self, row):
        self._row = row

    async def execute(self, *a, **kw):
        return _FakeResult(self._row)


def test_is_merchant_verified_true_when_row_exists():
    session = _FakeExecuteSession(row=(1,))
    result = asyncio.run(is_merchant_verified(session, "user-1"))
    assert result is True


def test_is_merchant_verified_false_when_no_row():
    session = _FakeExecuteSession(row=None)
    result = asyncio.run(is_merchant_verified(session, "user-1"))
    assert result is False


def test_require_merchant_verified_raises_when_not_verified():
    session = _FakeExecuteSession(row=None)
    with pytest.raises(MerchantNotVerifiedError):
        asyncio.run(require_merchant_verified(user_id="user-1", session=session))


def test_require_merchant_verified_returns_user_id_when_verified():
    session = _FakeExecuteSession(row=(1,))
    result = asyncio.run(require_merchant_verified(user_id="user-1", session=session))
    assert result == "user-1"


class _FakeUpsertSession:
    """grant_merchant_verification의 upsert 분기(이미 있으면 note만 갱신, 없으면
    새로 add)를 둘 다 검증하기 위한 세션 — scalar_one_or_none으로 기존 행 유무를
    흉내낸다."""

    def __init__(self, existing=None):
        self._existing = existing
        self.added = []
        self.deleted = []

    async def execute(self, *a, **kw):
        return self

    def scalar_one_or_none(self):
        return self._existing

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        self.deleted.append(obj)


def test_grant_merchant_verification_creates_new_row_when_absent():
    session = _FakeUpsertSession(existing=None)
    row = asyncio.run(grant_merchant_verification(session, "user-1", note="사업자등록증 확인함"))
    assert row.user_id == "user-1"
    assert row.note == "사업자등록증 확인함"
    assert session.added == [row]


def test_grant_merchant_verification_upserts_note_when_already_verified():
    from app.domain.merchant_verification import MerchantVerification

    existing = MerchantVerification(user_id="user-1", note="예전 메모")
    session = _FakeUpsertSession(existing=existing)
    row = asyncio.run(grant_merchant_verification(session, "user-1", note="갱신된 메모"))
    assert row is existing
    assert row.note == "갱신된 메모"
    assert session.added == []  # 새로 add하지 않고 기존 행만 갱신


def test_revoke_merchant_verification_returns_false_when_absent():
    session = _FakeUpsertSession(existing=None)
    result = asyncio.run(revoke_merchant_verification(session, "user-1"))
    assert result is False
    assert session.deleted == []


def test_revoke_merchant_verification_deletes_existing_row():
    from app.domain.merchant_verification import MerchantVerification

    existing = MerchantVerification(user_id="user-1")
    session = _FakeUpsertSession(existing=existing)
    result = asyncio.run(revoke_merchant_verification(session, "user-1"))
    assert result is True
    assert session.deleted == [existing]
