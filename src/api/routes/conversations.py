"""Persisted NL chat: conversations and messages scoped by X-Client-Session."""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Request
from starlette.responses import Response

from src.api.nl_engine import run_natural_language_query
from src.api.schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageRow,
    ConversationPatch,
    ConversationQueryRequest,
    ConversationSummary,
    NLQueryResponse,
)

router = APIRouter()

CLIENT_SESSION_HEADER = "x-client-session"
_MAX_HISTORY_MESSAGES = 60
_TITLE_MAX = 120


def _pool_or_503(store: Any) -> asyncpg.Pool:
    pool = getattr(store, "_pool", None) or getattr(store, "pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail="Chat persistence requires a PostgreSQL-backed API (not in-memory test store).",
        )
    return pool


def _parse_session(session_header: str | None) -> str:
    if not session_header or not session_header.strip():
        raise HTTPException(status_code=400, detail=f"Missing {CLIENT_SESSION_HEADER} header")
    sid = session_header.strip()
    if len(sid) > 128:
        raise HTTPException(status_code=400, detail="Invalid client session")
    # Accept UUID or opaque string (browser may use random hex)
    return sid


def _title_from_query(q: str) -> str:
    t = re.sub(r"\s+", " ", q.strip())
    if len(t) <= _TITLE_MAX:
        return t or "New chat"
    return t[: _TITLE_MAX - 1] + "…"


@router.get("/v1/conversations", response_model=ConversationListResponse)
async def list_conversations(
    request: Request,
    x_client_session: str | None = Header(default=None, alias="X-Client-Session"),
) -> ConversationListResponse:
    _parse_session(x_client_session)
    pool = _pool_or_503(request.app.state.store)
    sid = x_client_session.strip()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.client_session_id, c.title, c.created_at, c.updated_at,
                   COUNT(m.id)::int AS message_count
            FROM nl_conversations c
            LEFT JOIN nl_messages m ON m.conversation_id = c.id
            WHERE c.client_session_id = $1
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            LIMIT 200
            """,
            sid,
        )
    items = [
        ConversationSummary(
            id=str(r["id"]),
            client_session_id=r["client_session_id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            message_count=int(r["message_count"] or 0),
        )
        for r in rows
    ]
    return ConversationListResponse(conversations=items)


@router.post("/v1/conversations", response_model=ConversationSummary)
async def create_conversation(
    request: Request,
    body: ConversationCreate | None = None,
    x_client_session: str | None = Header(default=None, alias="X-Client-Session"),
) -> ConversationSummary:
    _parse_session(x_client_session)
    pool = _pool_or_503(request.app.state.store)
    sid = x_client_session.strip()
    title = (body.title.strip() if body and body.title else "") or "New chat"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO nl_conversations (client_session_id, title)
            VALUES ($1, $2)
            RETURNING id, client_session_id, title, created_at, updated_at
            """,
            sid,
            title,
        )
    return ConversationSummary(
        id=str(row["id"]),
        client_session_id=row["client_session_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=0,
    )


@router.get("/v1/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    request: Request,
    x_client_session: str | None = Header(default=None, alias="X-Client-Session"),
) -> ConversationDetailResponse:
    _parse_session(x_client_session)
    pool = _pool_or_503(request.app.state.store)
    sid = x_client_session.strip()
    try:
        cid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation id") from None
    async with pool.acquire() as conn:
        c = await conn.fetchrow(
            """
            SELECT id, client_session_id, title, created_at, updated_at
            FROM nl_conversations
            WHERE id = $1 AND client_session_id = $2
            """,
            cid,
            sid,
        )
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        mrows = await conn.fetch(
            """
            SELECT id, role, content, model, tokens_used, created_at
            FROM nl_messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            LIMIT 500
            """,
            cid,
        )
        mc = await conn.fetchval(
            "SELECT COUNT(*)::int FROM nl_messages WHERE conversation_id = $1",
            cid,
        )
    conv = ConversationSummary(
        id=str(c["id"]),
        client_session_id=c["client_session_id"],
        title=c["title"],
        created_at=c["created_at"],
        updated_at=c["updated_at"],
        message_count=int(mc or 0),
    )
    messages = [
        ConversationMessageRow(
            id=str(r["id"]),
            role=r["role"],
            content=r["content"],
            model=r["model"],
            tokens_used=r["tokens_used"],
            created_at=r["created_at"],
        )
        for r in mrows
    ]
    return ConversationDetailResponse(conversation=conv, messages=messages)


@router.patch("/v1/conversations/{conversation_id}", response_model=ConversationSummary)
async def patch_conversation(
    conversation_id: str,
    body: ConversationPatch,
    request: Request,
    x_client_session: str | None = Header(default=None, alias="X-Client-Session"),
) -> ConversationSummary:
    _parse_session(x_client_session)
    pool = _pool_or_503(request.app.state.store)
    sid = x_client_session.strip()
    try:
        cid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation id") from None
    title = body.title.strip() if body.title else None
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE nl_conversations SET title = $3, updated_at = NOW()
            WHERE id = $1 AND client_session_id = $2
            RETURNING id, client_session_id, title, created_at, updated_at
            """,
            cid,
            sid,
            title,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        mc = await conn.fetchval(
            "SELECT COUNT(*)::int FROM nl_messages WHERE conversation_id = $1",
            cid,
        )
    return ConversationSummary(
        id=str(row["id"]),
        client_session_id=row["client_session_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=int(mc or 0),
    )


@router.delete("/v1/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    request: Request,
    x_client_session: str | None = Header(default=None, alias="X-Client-Session"),
) -> Response:
    _parse_session(x_client_session)
    pool = _pool_or_503(request.app.state.store)
    sid = x_client_session.strip()
    try:
        cid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation id") from None
    async with pool.acquire() as conn:
        status = await conn.execute(
            "DELETE FROM nl_conversations WHERE id = $1 AND client_session_id = $2",
            cid,
            sid,
        )
    if status == "DELETE 0":
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=204)


@router.post("/v1/conversations/{conversation_id}/query", response_model=NLQueryResponse)
async def conversation_query(
    conversation_id: str,
    body: ConversationQueryRequest,
    request: Request,
    x_client_session: str | None = Header(default=None, alias="X-Client-Session"),
) -> NLQueryResponse:
    _parse_session(x_client_session)
    pool = _pool_or_503(request.app.state.store)
    store = request.app.state.store
    llm_client = request.app.state.llm_client
    sid = x_client_session.strip()
    try:
        cid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation id") from None

    q = body.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query required")

    async with pool.acquire() as conn:
        c = await conn.fetchrow(
            "SELECT id FROM nl_conversations WHERE id = $1 AND client_session_id = $2",
            cid,
            sid,
        )
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")

        prior = await conn.fetch(
            """
            SELECT role, content FROM nl_messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            cid,
            _MAX_HISTORY_MESSAGES,
        )
        prior_chrono = list(reversed(prior))
        is_first_user_message = len(prior) == 0

        await conn.execute(
            """
            INSERT INTO nl_messages (conversation_id, role, content)
            VALUES ($1, 'user', $2)
            """,
            cid,
            q,
        )

        if is_first_user_message:
            new_title = _title_from_query(q)
            await conn.execute(
                "UPDATE nl_conversations SET title = $2, updated_at = NOW() WHERE id = $1",
                cid,
                new_title,
            )

    messages: list[dict[str, Any]] = []
    for row in prior_chrono:
        messages.append({"role": row["role"], "content": row["content"]})
    messages.append({"role": "user", "content": q})

    result = await run_natural_language_query(store, llm_client, messages)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO nl_messages (conversation_id, role, content, model, tokens_used)
            VALUES ($1, 'assistant', $2, $3, $4)
            """,
            cid,
            result.answer,
            result.model,
            result.tokens_used,
        )
        await conn.execute(
            "UPDATE nl_conversations SET updated_at = NOW() WHERE id = $1",
            cid,
        )

    return result
