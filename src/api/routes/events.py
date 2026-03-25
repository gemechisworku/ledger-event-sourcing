"""
Event inspection — browse streams, view individual events, compare
upcasted read-path vs raw persisted payload.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


def _require_pg(request: Request) -> Any:
    store = request.app.state.store
    if getattr(store, "_pool", None) is None:
        raise HTTPException(503, "Event inspection requires the PostgreSQL-backed API.")
    return store


def _event_json(ev: Any) -> dict[str, Any]:
    return {
        "event_id": str(ev.event_id),
        "stream_id": ev.stream_id,
        "stream_position": ev.stream_position,
        "global_position": ev.global_position,
        "event_type": ev.event_type,
        "event_version": ev.event_version,
        "payload": dict(ev.payload) if isinstance(ev.payload, dict) else ev.payload,
        "metadata": dict(ev.metadata) if isinstance(ev.metadata, dict) else ev.metadata,
        "recorded_at": str(ev.recorded_at) if ev.recorded_at else None,
    }


@router.get("/v1/streams/{stream_id:path}")
async def browse_stream(
    request: Request,
    stream_id: str,
    from_position: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    """Load events from any stream by stream_id."""
    store = _require_pg(request)
    events = await store.load_stream(stream_id, from_position=from_position)
    truncated = events[:limit]
    return {
        "stream_id": stream_id,
        "from_position": from_position,
        "event_count": len(truncated),
        "has_more": len(events) > limit,
        "events": [_event_json(e) for e in truncated],
    }


@router.get("/v1/events/upcastable")
async def find_upcastable_event(request: Request) -> dict[str, Any]:
    """
    Auto-discover a v1 event eligible for upcasting (CreditAnalysisCompleted or
    DecisionGenerated stored as v1). Returns its event_id so the frontend can
    immediately load the comparison without manual UUID entry.
    """
    store = _require_pg(request)
    assert store._pool is not None
    async with store._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT event_id, event_type, event_version
            FROM events
            WHERE event_version = 1
              AND event_type IN ('CreditAnalysisCompleted', 'DecisionGenerated')
            ORDER BY global_position DESC
            LIMIT 1
            """
        )
    if not row:
        return {
            "found": False,
            "event_id": None,
            "hint": "No v1 events exist yet. Run a pipeline so the seeded v1 events are present.",
        }
    return {
        "found": True,
        "event_id": str(row["event_id"]),
        "event_type": row["event_type"],
        "stored_event_version": int(row["event_version"]),
    }


@router.get("/v1/events/{event_id}")
async def get_event(request: Request, event_id: str) -> dict[str, Any]:
    """Load a single event by event_id (upcasted read path)."""
    store = _require_pg(request)
    try:
        eid = UUID(event_id)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid event_id: {exc}") from exc

    ev = await store.get_event(eid)
    if not ev:
        raise HTTPException(404, "Event not found")
    return _event_json(ev)


@router.get("/v1/events/{event_id}/upcast-compare")
async def upcast_compare(request: Request, event_id: str) -> dict[str, Any]:
    """
    Side-by-side: the upcasted read-path view vs the raw persisted payload.
    Demonstrates that stored bytes are never mutated by upcasting.
    """
    store = _require_pg(request)
    try:
        eid = UUID(event_id)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid event_id: {exc}") from exc

    upcasted = await store.get_event(eid)
    raw = await store.get_event_raw(eid)
    if not raw or not upcasted:
        raise HTTPException(404, "Event not found")

    version_changed = raw.event_version != upcasted.event_version
    added_fields: list[str] = []
    if version_changed and isinstance(upcasted.payload, dict) and isinstance(raw.payload, dict):
        added_fields = sorted(set(upcasted.payload.keys()) - set(raw.payload.keys()))

    return {
        "event_id": event_id,
        "upcasted": _event_json(upcasted),
        "raw": _event_json(raw),
        "analysis": {
            "stored_version": raw.event_version,
            "read_path_version": upcasted.event_version,
            "version_changed_by_upcast": version_changed,
            "fields_added_by_upcast": added_fields,
            "raw_payload_unchanged": True,
        },
    }
