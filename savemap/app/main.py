from pathlib import Path

from fastapi import FastAPI
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

    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()
