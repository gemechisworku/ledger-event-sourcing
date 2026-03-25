from fastapi import APIRouter

from src.api.routes import agents, applications, conversations, events, health, pipeline, query

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(applications.router, tags=["applications"])
api_router.include_router(pipeline.router, tags=["pipeline"])
api_router.include_router(query.router, tags=["query"])
api_router.include_router(conversations.router, tags=["conversations"])
api_router.include_router(agents.router, tags=["agents"])
api_router.include_router(events.router, tags=["events"])

__all__ = ["api_router"]
