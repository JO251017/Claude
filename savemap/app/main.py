from fastapi import FastAPI

from app.api.v1 import api_router
from app.core.config import settings


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

    return app


app = create_app()
