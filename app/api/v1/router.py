from fastapi import APIRouter

from app.api.v1.endpoints import artifacts, convert, health

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(convert.router, tags=["Convert"])
api_router.include_router(artifacts.router, tags=["Artifacts"])
