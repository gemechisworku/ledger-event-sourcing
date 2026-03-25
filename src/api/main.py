"""
FastAPI ASGI app — async HTTP + SSE pipeline progress.

Run: uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from unittest.mock import AsyncMock, MagicMock

import dotenv

from src.api.services.jobs import JobRegistry
from src.event_store import EventStore
from src.upcasters import default_upcaster_registry


def _build_anthropic_client() -> Any:
    """Real Anthropic when ANTHROPIC_API_KEY is set; else deterministic mocks for LLM-using agents."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return AsyncAnthropic(api_key=key)

    async def fake_create(*_args: Any, **kwargs: Any) -> Any:
        system = str(kwargs.get("system") or "")
        user_parts = []
        for m in kwargs.get("messages") or []:
            user_parts.append(str(m.get("content", "")))
        user_blob = " ".join(user_parts).lower()
        sys_l = system.lower()
        if "fraud screening assistant" in sys_l or ("fraud_score" in sys_l and "anomalies" in sys_l):
            text = '{"fraud_score":0.12,"recommendation":"CLEAR","anomalies":[]}'
        elif "loan orchestrator" in sys_l:
            text = (
                '{"recommendation":"REFER","confidence":0.65,'
                '"executive_summary":"Deterministic API mock — review recommended."}'
            )
        else:
            text = (
                '{"risk_tier":"MEDIUM","recommended_limit_usd":400000,'
                '"confidence":0.82,"rationale":"API default deterministic JSON.",'
                '"key_concerns":[],"data_quality_caveats":[],"policy_overrides_applied":[]}'
            )

        class Usage:
            input_tokens = 100
            output_tokens = 200

        class Block:
            pass

        Block.text = text

        class Resp:
            content = [Block()]
            usage = Usage()

        return Resp()

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=fake_create)
    return client


def create_app(
    *,
    store: Any | None = None,
    anthropic: Any | None = None,
    jobs: Any | None = None,
) -> FastAPI:
    """Create FastAPI app. Pass `store` (e.g. InMemoryEventStore) for tests; otherwise uses DATABASE_URL."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if store is not None:
            app.state.store = store
            app.state.anthropic = anthropic if anthropic is not None else _build_anthropic_client()
            app.state.jobs = jobs if jobs is not None else JobRegistry()
        else:
            dotenv.load_dotenv(Path(__file__).resolve().parents[2] / ".env")
            url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DB_URL")
            if not url:
                raise RuntimeError("DATABASE_URL or TEST_DB_URL required when store is not injected")
            st = EventStore(url, upcaster_registry=default_upcaster_registry())
            await st.connect()
            app.state.store = st
            app.state.anthropic = anthropic if anthropic is not None else _build_anthropic_client()
            app.state.jobs = jobs if jobs is not None else JobRegistry()
        yield
        if store is None:
            await app.state.store.close()

    app = FastAPI(lifespan=lifespan, title="Ledger API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from src.api.routes import api_router

    app.include_router(api_router)

    return app


app = create_app()
