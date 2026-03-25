"""Natural-language query endpoint — LLM function calling over the event store."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from src.api.nl_engine import run_natural_language_query
from src.api.schemas import NLQueryRequest, NLQueryResponse

router = APIRouter()

# Standalone queries: cap prior turns sent to the model (user/assistant messages only).
_MAX_PRIOR_MESSAGES = 60


@router.post("/v1/query", response_model=NLQueryResponse)
async def natural_language_query(body: NLQueryRequest, request: Request) -> NLQueryResponse:
    store = request.app.state.store
    llm_client = request.app.state.llm_client

    messages: list[dict[str, Any]] = []
    for h in body.history[-_MAX_PRIOR_MESSAGES:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": body.query})
    return await run_natural_language_query(store, llm_client, messages)
