import asyncio
from unittest.mock import patch

import pytest
from jose import jwt

from app.api.deps import current_user_id, require_admin_key, require_user_id
from app.core.errors import AuthenticationRequiredError


def _token(secret: str = "test-secret", sub: str = "user-123") -> str:
    return jwt.encode({"sub": sub, "aud": "authenticated"}, secret, algorithm="HS256")


def test_require_user_id_raises_without_header():
    with pytest.raises(AuthenticationRequiredError):
        asyncio.run(require_user_id(None))


def test_require_user_id_raises_with_invalid_token():
    with pytest.raises(AuthenticationRequiredError):
        asyncio.run(require_user_id("Bearer not-a-real-token"))


def test_require_user_id_returns_sub_with_valid_token():
    with patch("app.core.security.settings.supabase_jwt_secret", "test-secret"):
        token = _token()
        result = asyncio.run(require_user_id(f"Bearer {token}"))
    assert result == "user-123"


def test_current_user_id_falls_back_to_anonymous_without_header():
    result = asyncio.run(current_user_id(None))
    assert result == "anonymous"


def test_current_user_id_falls_back_to_anonymous_on_wrong_secret():
    token = _token(secret="wrong-secret")
    with patch("app.core.security.settings.supabase_jwt_secret", "test-secret"):
        result = asyncio.run(current_user_id(f"Bearer {token}"))
    assert result == "anonymous"


def test_require_admin_key_rejects_when_not_configured():
    # ADMIN_SYNC_KEY를 아예 안 넣었으면(빈 문자열) 어떤 값을 보내도 항상 거부 —
    # "설정 안 하면 관리자 API 자체가 잠긴다"는 안전장치.
    with patch("app.api.deps.settings.admin_sync_key", ""):
        with pytest.raises(AuthenticationRequiredError):
            asyncio.run(require_admin_key("anything"))


def test_require_admin_key_rejects_missing_header():
    with patch("app.api.deps.settings.admin_sync_key", "real-secret"):
        with pytest.raises(AuthenticationRequiredError):
            asyncio.run(require_admin_key(None))


def test_require_admin_key_rejects_wrong_key():
    with patch("app.api.deps.settings.admin_sync_key", "real-secret"):
        with pytest.raises(AuthenticationRequiredError):
            asyncio.run(require_admin_key("wrong-guess"))


def test_require_admin_key_accepts_correct_key():
    with patch("app.api.deps.settings.admin_sync_key", "real-secret"):
        # 예외 없이 통과해야 한다
        asyncio.run(require_admin_key("real-secret"))


def test_require_admin_key_uses_constant_time_comparison(monkeypatch):
    # `!=` 대신 secrets.compare_digest를 실제로 쓰는지 — 직접 스파이해서 확인한다.
    import app.api.deps as deps_module

    calls = []
    original = deps_module.secrets.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(deps_module.secrets, "compare_digest", spy)
    monkeypatch.setattr(deps_module.settings, "admin_sync_key", "real-secret")

    with pytest.raises(AuthenticationRequiredError):
        asyncio.run(require_admin_key("wrong-guess"))

    assert calls == [("wrong-guess", "real-secret")]
