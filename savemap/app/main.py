import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import settings
from app.core.db import engine
from app.core.redis import redis_client

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
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

    return app


app = create_app()
