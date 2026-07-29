from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import AuthenticationRequiredError
from app.core.security import decode_supabase_jwt


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


def _decode_bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        claims = decode_supabase_jwt(token)
    except ValueError:
        return None
    return claims.get("sub")


async def current_user_id(authorization: str | None = Header(default=None)) -> str:
    return _decode_bearer(authorization) or "anonymous"


async def require_user_id(authorization: str | None = Header(default=None)) -> str:
    user_id = _decode_bearer(authorization)
    if not user_id:
        raise AuthenticationRequiredError()
    return user_id


SessionDep = Depends(db_session)
UserDep = Depends(current_user_id)
RequireUserDep = Depends(require_user_id)
