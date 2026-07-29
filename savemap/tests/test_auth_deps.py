import asyncio
from unittest.mock import patch

import pytest
from jose import jwt

from app.api.deps import current_user_id, require_user_id
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
