from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    store = request.app.state.store
    pool = getattr(store, "_pool", None) or getattr(store, "pool", None)
    db_status = "in-memory"
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_status = "ok"
        except Exception:
            db_status = "error"
    return HealthResponse(status="ok", database=db_status, store_pool=pool is not None)
