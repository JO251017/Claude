from fastapi import APIRouter

from app.api.v1 import (
    admin,
    exchange,
    geo,
    merchant,
    places,
    reports,
    route,
    savings,
    search,
    users,
    verifications,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(search.router)
api_router.include_router(route.router)
api_router.include_router(reports.router)
api_router.include_router(verifications.router)
api_router.include_router(merchant.router)
api_router.include_router(users.router)
api_router.include_router(savings.router)
api_router.include_router(exchange.router)
api_router.include_router(geo.router)
api_router.include_router(admin.router)
api_router.include_router(places.router)
