from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_supabase_jwt


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


async def current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        return "anonymous"
    token = authorization.split(" ", 1)[1]
    try:
        claims = decode_supabase_jwt(token)
    except ValueError:
        return "anonymous"
    return claims.get("sub", "anonymous")


SessionDep = Depends(db_session)
UserDep = Depends(current_user_id)
