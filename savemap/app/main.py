import json
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import settings
from app.core.db import engine
from app.core.redis import redis_client

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def create_app() -> FastAPI:
    app = FastAPI(
        title="SaveMap API",
        version="0.1.0",
        debug=settings.app_debug,
    )
    app.include_router(api_router)

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
