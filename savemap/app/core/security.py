import secrets
import time

import httpx
from jose import JWTError, jwk, jwt

from app.core.config import settings

# Supabase 프로젝트는 두 가지 JWT 서명 방식이 있다:
#   1) 레거시: JWT Secret 기반 대칭키(HS256) — SUPABASE_JWT_SECRET
#   2) 신규: 비대칭 서명 키(ES256/RS256) — JWKS 엔드포인트에서 공개키를 받아 검증
# 어느 쪽인지는 토큰 헤더의 alg 값으로 자동 판별한다. (실제 배포본에서 받은 토큰이
# ES256으로 서명되어 있어 HS256 고정 검증이 항상 실패하고 있었음 — 이전 버전의 버그)
_jwks_cache: dict = {"keys": [], "fetched_at": 0.0}
_JWKS_TTL_SEC = 3600


async def _fetch_jwks() -> list[dict]:
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json().get("keys", [])


async def _get_jwks(force_refresh: bool = False) -> list[dict]:
    now = time.time()
    if not force_refresh and _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < _JWKS_TTL_SEC:
        return _jwks_cache["keys"]
    keys = await _fetch_jwks()
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


async def decode_supabase_jwt(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise ValueError("invalid token") from exc

    alg = header.get("alg", "HS256")

    if alg == "HS256":
        try:
            return jwt.decode(
                token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated"
            )
        except JWTError as exc:
            raise ValueError("invalid token") from exc

    kid = header.get("kid")
    keys = await _get_jwks()
    matching = next((k for k in keys if k.get("kid") == kid), None)
    if matching is None:
        # 키가 회전됐을 수 있으니 캐시를 강제로 한 번 더 갱신해서 재시도
        keys = await _get_jwks(force_refresh=True)
        matching = next((k for k in keys if k.get("kid") == kid), None)
    if matching is None:
        raise ValueError("unknown signing key")

    try:
        public_key = jwk.construct(matching, alg)
        return jwt.decode(token, public_key, algorithms=[alg], audience="authenticated")
    except JWTError as exc:
        raise ValueError("invalid token") from exc


class PartnerOAuthTokenProvider:
    def __init__(self, partner: str):
        self.partner = partner

    async def get_token(self) -> str:
        raise NotImplementedError(
            f"{self.partner} OAuth2 토큰 발급은 실제 파트너 스펙 확인 후 구현 (미확인)"
        )


def admin_key_matches(candidate: str | None) -> bool:
    """관리자 키(X-Admin-Key)가 설정값과 일치하는지 타이밍에 안전하게 비교한다.

    secrets.compare_digest는 str을 받으면 두 값이 모두 ASCII일 때만 동작하고, 아니면
    `TypeError: comparing strings with non-ASCII characters is not supported`를 던진다.
    그래서 사용자가 실수로 한글이 섞인 값을 X-Admin-Key로 보내면 인증 실패(401)가
    아니라 처리되지 않은 예외 → 500이 나버렸다(2026-08-19 실데이터 동기화 실행에서
    모든 요청이 이 500으로 실패). 바이트로 바꿔서 비교하면 내용에 상관없이 상수시간
    비교가 그대로 유지되면서 이 문제가 사라진다.
    """
    if not settings.admin_sync_key or not candidate:
        return False
    return secrets.compare_digest(
        candidate.encode("utf-8"), settings.admin_sync_key.encode("utf-8")
    )
