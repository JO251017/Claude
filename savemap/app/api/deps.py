import secrets
from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.errors import AuthenticationRequiredError
from app.core.security import decode_supabase_jwt


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


async def _decode_bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        claims = await decode_supabase_jwt(token)
    except ValueError:
        return None
    return claims.get("sub")


async def current_user_id(authorization: str | None = Header(default=None)) -> str:
    return await _decode_bearer(authorization) or "anonymous"


async def require_user_id(authorization: str | None = Header(default=None)) -> str:
    user_id = await _decode_bearer(authorization)
    if not user_id:
        raise AuthenticationRequiredError()
    return user_id


async def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """관리자 전용 엔드포인트 공통 인증 — ADMIN_SYNC_KEY가 설정 안 돼 있으면 어떤 키를
    보내도 항상 거부한다. 단순 `!=` 문자열 비교는 일치하는 접두 길이에 따라 비교
    시간이 미세하게 달라질 수 있어(타이밍 공격 이론상 가능) secrets.compare_digest로
    상수시간 비교한다 — admin.py 7곳에 흩어져 있던 동일한 (그리고 타이밍에 안전하지
    않던) 검사를 여기 하나로 모았다(2026-08-12)."""
    if not settings.admin_sync_key or not x_admin_key:
        raise AuthenticationRequiredError("관리자 키가 필요합니다 (X-Admin-Key 헤더)")
    if not secrets.compare_digest(x_admin_key, settings.admin_sync_key):
        raise AuthenticationRequiredError("관리자 키가 필요합니다 (X-Admin-Key 헤더)")


SessionDep = Depends(db_session)
UserDep = Depends(current_user_id)
RequireUserDep = Depends(require_user_id)
RequireAdminDep = Depends(require_admin_key)
