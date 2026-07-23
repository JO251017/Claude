from fastapi import APIRouter

from app.api.v1 import merchant, reports, search, verifications

api_router = APIRouter(prefix="/v1")
api_router.include_router(search.router)
api_router.include_router(reports.router)
api_router.include_router(verifications.router)
api_router.include_router(merchant.router)
