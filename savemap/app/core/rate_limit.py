import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.core.config import settings

# 지금까지 /search, /reports, admin 엔드포인트 어디에도 요청 횟수 제한이 없었다
# (2026-08-12 품질 점검에서 확인) — Render 무료 플랜은 인스턴스가 하나뿐이라
# 수평 확장이 없으니, Redis 없이 프로세스 메모리 카운터로도 충분하다. 재시작되면
# 카운터가 리셋되는데, 이 용도(무제한 남용 방지)엔 그걸로 충분하다 — 정밀한
# 분산 레이트리밋이 필요한 게 아니라, "봇이 한도 없이 두들기는 걸" 막는 안전판이다.
WINDOW_SEC = 60
ADMIN_LIMIT = 20  # 관리자 엔드포인트는 더 엄격하게 — 키 브루트포스 시도도 늦춘다
# ADMIN_LIMIT의 목적은 위 주석대로 "키 브루트포스 억제"인데, 키가 **맞는** 요청까지
# 분당 20건으로 묶으면 정작 정상 운영이 막힌다 — 인허가 데이터 동기화는 한 지역·업종만
# 해도 페이지가 수백 개라, 20/분으로는 절대 못 끝내고 중간에 429로 끊긴다(2026-08-19
# 실제 동기화 실행에서 확인). 올바른 키를 제시한 요청은 정의상 브루트포스가 아니므로
# 별도 버킷에서 훨씬 넉넉하게 허용하고, 키가 없거나 틀린 요청만 20/분으로 묶는다.
ADMIN_AUTHED_LIMIT = 240
DEFAULT_LIMIT = 120
# 헬스체크(Render 자체 헬스체크 + 이 프로젝트의 keep-alive 핑)는 정상적으로 자주
# 호출되므로 제한 대상에서 뺀다 — 안 빼면 keep-alive가 스스로를 429로 막아버릴 수 있다.
EXEMPT_PREFIXES = ("/health", "/config.js")

# 모듈 전역으로 둔다 — 이 파일의 다른 캐시들(discovery._kakao_cache,
# good_price._IMPORT_JOBS)과 같은 패턴이고, 테스트에서 앱 재생성 없이
# `_buckets.clear()`로 바로 초기화할 수 있다(BaseHTTPMiddleware 인스턴스는
# Starlette가 지연 생성해서 테스트 쪽에서 직접 붙잡기 까다롭다).
_buckets: dict[tuple[str, str], tuple[int, int]] = {}
_last_prune_at: float = 0.0


def _client_ip(request: Request) -> str:
    """Render는 프록시 뒤에서 컨테이너를 돌리는데, uvicorn을 --proxy-headers 없이
    띄우면 request.client.host가 실제 방문자가 아니라 프록시 주소로 잡혀서, 사실상
    "모든 사용자를 하나로 묶어" 제한하는 꼴이 된다 — 그럼 레이트리밋이 개별 남용자를
    막는 게 아니라 서비스 전체를 잠그는 역효과가 난다. X-Forwarded-For를 직접
    읽어서(가장 왼쪽 = 최초 클라이언트) 이 문제를 피한다."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_valid_admin_key(admin_key: str | None) -> bool:
    """deps.require_admin_key와 같은 판정을 미들웨어 단계에서 한 번 더 한다(상수시간
    비교도 동일). 여기서 통과시켜도 실제 인증은 라우트 의존성이 다시 하므로,
    이 함수의 역할은 "어느 카운터 버킷을 쓸지" 고르는 것뿐이다."""
    if not settings.admin_sync_key or not admin_key:
        return False
    return secrets.compare_digest(admin_key, settings.admin_sync_key)


def _limit_for(path: str, admin_key: str | None = None) -> tuple[str, int] | None:
    if any(path.startswith(p) for p in EXEMPT_PREFIXES):
        return None
    if path.startswith("/v1/admin"):
        if _is_valid_admin_key(admin_key):
            return "admin_authed", ADMIN_AUTHED_LIMIT
        return "admin", ADMIN_LIMIT
    if path.startswith("/v1/"):
        return "api", DEFAULT_LIMIT
    return None  # 정적 프론트 파일 등은 제한 대상 아님


def _prune_stale_buckets(now: float) -> None:
    global _last_prune_at
    # 매 요청마다 전체를 훑으면 낭비니, 한 윈도우에 한 번 정도만 정리한다.
    if now - _last_prune_at < WINDOW_SEC:
        return
    current_window = int(now // WINDOW_SEC)
    stale_keys = [k for k, (w, _) in _buckets.items() if w < current_window - 1]
    for key in stale_keys:
        del _buckets[key]
    _last_prune_at = now


def _check_and_increment(ip: str, group: str, limit: int) -> bool:
    """이번 요청까지 세고, 한도를 넘었으면 False(거부)를 돌려준다."""
    now = time.time()
    window = int(now // WINDOW_SEC)
    key = (ip, group)

    stored_window, count = _buckets.get(key, (window, 0))
    if stored_window != window:
        stored_window, count = window, 0
    count += 1
    _buckets[key] = (stored_window, count)

    _prune_stale_buckets(now)
    return count <= limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        group_limit = _limit_for(request.url.path, request.headers.get("x-admin-key"))
        if group_limit is None:
            return await call_next(request)
        group, limit = group_limit

        if not _check_and_increment(_client_ip(request), group, limit):
            return JSONResponse(
                status_code=429,
                content={"code": "SM4291", "message": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."},
                headers={"Retry-After": str(WINDOW_SEC)},
            )
        return await call_next(request)
