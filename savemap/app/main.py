import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import settings
from app.core.db import engine
from app.core.observability import configure_logging, configure_sentry
from app.core.rate_limit import RateLimitMiddleware
from app.core.redis import redis_client

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    configure_sentry()

    app = FastAPI(
        title="SaveMap API",
        version="0.1.0",
        debug=settings.app_debug,
    )
    app.include_router(api_router)

    # 우리 SaveMapError 계열이 아닌 예상 못 한 예외(DB 컬럼 길이 초과 등)는 기본적으로
    # FastAPI가 빈 본문의 500만 돌려줘서, 실제로 뭐가 터졌는지 알 방법이 없었다
    # (착한가격업소 대량 임포트에서 "HTTP 500: null"만 보이던 문제). 항상 원인을 담은
    # JSON을 돌려주게 한다 — 전체 트레이스백은 노출하지 않고 예외 종류/메시지까지만.
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("처리되지 않은 예외: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "code": "SM5000",
                "message": f"{exc.__class__.__name__}: {exc}"[:500],
            },
        )

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    @app.get("/health/deps", tags=["meta"])
    async def health_deps() -> dict:
        result = {"db": "unknown", "redis": "unknown"}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            result["db"] = "ok"
        except Exception as exc:
            result["db"] = f"error: {exc}"
        try:
            await redis_client.ping()
            result["redis"] = "ok"
        except Exception as exc:
            result["redis"] = f"error: {exc}"
        return result

    @app.get("/config.js", tags=["meta"])
    async def frontend_config() -> Response:
        config = {
            "supabaseUrl": settings.supabase_url,
            "supabaseAnonKey": settings.supabase_anon_key,
            # AI 절약 플랜 노출 여부 — 백엔드 settings.ai_saving_plan_enabled가 유일한
            # 진실 소스다. 프론트가 별도로 하드코딩한 값을 갖지 않고 이걸 그대로
            # 읽는다(app.js가 이미 부팅 전에 이 스크립트를 로드하므로 별도 fetch 불필요).
            "aiSavingPlanEnabled": settings.ai_saving_plan_enabled,
        }
        body = f"window.SAVEMAP_CONFIG = {json.dumps(config)};"
        return Response(content=body, media_type="application/javascript")

    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

        # 배포 후에도 브라우저가 옛 index.html을 계속 쓰면 (index가 참조하는 ?v= 버전이
        # 안 바뀌어서) 새 기능이 "안 뜨는" 것처럼 보인다 — HTML은 항상 서버에 재검증하게 한다.
        @app.middleware("http")
        async def no_cache_html(request, call_next):
            response = await call_next(request)
            if "text/html" in (response.headers.get("content-type") or ""):
                response.headers["Cache-Control"] = "no-cache"
            return response

    # 요청 제한(RateLimitMiddleware)보다 먼저 등록해서 더 안쪽에 둔다 — CORS는
    # preflight(OPTIONS) 요청과 에러 응답(429 포함)에도 항상 CORS 헤더가 실려야
    # 브라우저가 "CORS 실패"가 아니라 실제 에러(429 등)로 인식하기 때문에, 가장
    # 나중에 추가해서(= 가장 바깥쪽) 어떤 안쪽 미들웨어가 요청을 막아도 CORS 헤더는
    # 항상 붙게 한다. cors_allowed_origins가 비어있으면(기본값) 아예 안 붙여서
    # 지금까지의 동작(같은 도메인 프론트만 호출 가능)을 그대로 유지한다.
    app.add_middleware(RateLimitMiddleware)

    allowed_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    return app


app = create_app()
