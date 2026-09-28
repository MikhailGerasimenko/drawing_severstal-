from fastapi import APIRouter, Depends

from app.api.v1.endpoints import artifacts, convert, health
from app.core.security import verify_internal_token

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(
    convert.router,
    tags=["Convert"],
    dependencies=[Depends(verify_internal_token)],
)
api_router.include_router(
    artifacts.router,
    tags=["Artifacts"],
    dependencies=[Depends(verify_internal_token)],
)
