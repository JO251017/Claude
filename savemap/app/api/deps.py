from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import AuthenticationRequiredError, MerchantNotVerifiedError
from app.core.security import admin_key_matches, decode_supabase_jwt
from app.sources.merchant_console.service import is_merchant_verified


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


async def require_merchant_verified(
    user_id: str = Depends(require_user_id),
    session: AsyncSession = Depends(db_session),
) -> str:
    """사업자 콘솔 접근 제어(2-3, 2026-08-13) — 로그인만으론 부족하고
    merchant_verification에 이 user_id 행이 있어야 통과한다. "사업자 콘솔은
    추후에 사업자 증명된 사용자만 보이도록"(사용자 지시) — 프론트에서 버튼을
    숨기는 것과 별개로, 숨긴 버튼을 안 눌러도 API를 직접 두드리면 뚫리지 않도록
    서버에서도 실제로 막는다."""
    if not await is_merchant_verified(session, user_id):
        raise MerchantNotVerifiedError()
    return user_id


async def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """관리자 전용 엔드포인트 공통 인증 — ADMIN_SYNC_KEY가 설정 안 돼 있으면 어떤 키를
    보내도 항상 거부한다. 단순 `!=` 문자열 비교는 일치하는 접두 길이에 따라 비교
    시간이 미세하게 달라질 수 있어(타이밍 공격 이론상 가능) secrets.compare_digest로
    상수시간 비교한다 — admin.py 7곳에 흩어져 있던 동일한 (그리고 타이밍에 안전하지
    않던) 검사를 여기 하나로 모았다(2026-08-12). 실제 비교는 security.admin_key_matches가
    하고, 레이트리밋 미들웨어도 같은 함수를 써서 판정이 갈리지 않게 한다."""
    if not admin_key_matches(x_admin_key):
        raise AuthenticationRequiredError("관리자 키가 필요합니다 (X-Admin-Key 헤더)")


SessionDep = Depends(db_session)
UserDep = Depends(current_user_id)
RequireUserDep = Depends(require_user_id)
RequireAdminDep = Depends(require_admin_key)
RequireMerchantVerifiedDep = Depends(require_merchant_verified)
