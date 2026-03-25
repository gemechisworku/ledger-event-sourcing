"""
FastAPI ASGI app — async HTTP + SSE pipeline progress.

Run: uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import dotenv

from src.api.services.jobs import JobRegistry
from src.event_store import EventStore
from src.upcasters import default_upcaster_registry


def _build_llm_client() -> Any:
    """Real OpenRouter when OPENROUTER_API_KEY is set; mock when MOCK_LLM=true or key missing."""
    if os.environ.get("MOCK_LLM", "").strip().lower() in ("1", "true", "yes"):
        from src.llm_client import build_mock_llm_client
        return build_mock_llm_client()

    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        from src.llm_client import build_llm_client
        return build_llm_client()

    from src.llm_client import build_mock_llm_client
    return build_mock_llm_client()


def create_app(
    *,
    store: Any | None = None,
    llm: Any | None = None,
    jobs: Any | None = None,
) -> FastAPI:
    """Create FastAPI app. Pass `store` (e.g. InMemoryEventStore) for tests; otherwise uses DATABASE_URL."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if store is not None:
            app.state.store = store
            app.state.llm_client = llm if llm is not None else _build_llm_client()
            app.state.jobs = jobs if jobs is not None else JobRegistry()
        else:
            dotenv.load_dotenv(Path(__file__).resolve().parents[2] / ".env")
            url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DB_URL")
            if not url:
                raise RuntimeError("DATABASE_URL or TEST_DB_URL required when store is not injected")
            st = EventStore(url, upcaster_registry=default_upcaster_registry())
            await st.connect()
            app.state.store = st
            app.state.llm_client = llm if llm is not None else _build_llm_client()
            app.state.jobs = jobs if jobs is not None else JobRegistry()
        yield
        if store is None:
            await app.state.store.close()

    app = FastAPI(lifespan=lifespan, title="Ledger API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
        ).split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from src.api.routes import api_router

    app.include_router(api_router)

    return app


app = create_app()
