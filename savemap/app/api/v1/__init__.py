from fastapi import APIRouter

from app.api.v1 import exchange, merchant, reports, savings, search, users, verifications

api_router = APIRouter(prefix="/v1")
api_router.include_router(search.router)
api_router.include_router(reports.router)
api_router.include_router(verifications.router)
api_router.include_router(merchant.router)
api_router.include_router(users.router)
api_router.include_router(savings.router)
api_router.include_router(exchange.router)
