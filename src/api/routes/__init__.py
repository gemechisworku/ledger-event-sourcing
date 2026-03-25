from fastapi import APIRouter

from src.api.routes import applications, health, pipeline

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(applications.router, tags=["applications"])
api_router.include_router(pipeline.router, tags=["pipeline"])

__all__ = ["api_router"]
