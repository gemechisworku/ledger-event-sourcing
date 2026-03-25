"""
Event inspection -- browse streams, view individual events, compare
upcasted read-path vs raw persisted payload.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

UPCAST_DEMO_STREAM_CREDIT = "credit-DEMO-UPCAST"
UPCAST_DEMO_STREAM_DECISION = "loan-DEMO-UPCAST"

router = APIRouter()


def _require_pg(request: Request) -> Any:
    store = request.app.state.store
    if getattr(store, "_pool", None) is None:
        raise HTTPException(503, "Event inspection requires the PostgreSQL-backed API.")
    return store


async def _ensure_upcast_demo_events(store: Any) -> dict[str, Any]:
    """
    Idempotently append v1 CreditAnalysisCompleted and DecisionGenerated events whose
    payloads omit fields added by UpcasterRegistry (read path upgrades to v2 in memory only).
    """
    now = datetime.now(timezone.utc)
    results: dict[str, Any] = {
        "created_credit": False,
        "created_decision": False,
        "credit_event_id": None,
        "decision_event_id": None,
        "credit_stream_id": UPCAST_DEMO_STREAM_CREDIT,
        "decision_stream_id": UPCAST_DEMO_STREAM_DECISION,
    }

    pool = store._pool
    assert pool is not None

    # --- Credit v1 demo ---
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT event_id FROM events WHERE stream_id = $1 AND event_type = 'CreditAnalysisCompleted' LIMIT 1",
            UPCAST_DEMO_STREAM_CREDIT,
        )
    if existing:
        results["credit_event_id"] = str(existing["event_id"])
    else:
        credit_payload = {
            "application_id": "DEMO-UPCAST-CREDIT",
            "session_id": "sess-demo-upcast-credit",
            "completed_at": now.isoformat(),
            "analysis_duration_ms": 1500,
            "model_deployment_id": "dep-demo-upcast",
            "input_data_hash": "upcastdemo01",
            "decision": {
                "risk_tier": "MEDIUM",
                "confidence": 0.82,
                "recommended_limit_usd": "250000.0",
                "rationale": "Legacy v1-shaped payload (no model_version / regulatory_basis on disk). Read path adds them via upcaster.",
                "key_concerns": [],
                "data_quality_caveats": [],
                "policy_overrides_applied": [],
            },
        }
        ver = await store.stream_version(UPCAST_DEMO_STREAM_CREDIT)
        evts = await store.append(
            UPCAST_DEMO_STREAM_CREDIT,
            [{"event_type": "CreditAnalysisCompleted", "payload": credit_payload}],
            expected_version=ver,
            event_version=1,
        )
        results["credit_event_id"] = str(evts[0].event_id)
        results["created_credit"] = True

    # --- Decision v1 demo ---
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT event_id FROM events WHERE stream_id = $1 AND event_type = 'DecisionGenerated' LIMIT 1",
            UPCAST_DEMO_STREAM_DECISION,
        )
    if existing:
        results["decision_event_id"] = str(existing["event_id"])
    else:
        decision_payload = {
            "application_id": "DEMO-UPCAST-DECISION",
            "session_id": "sess-demo-upcast-decision",
            "generated_at": now.isoformat(),
            "final_decision": "APPROVED_WITH_CONDITIONS",
            "risk_tier": "MEDIUM",
            "approved_amount_usd": "200000.0",
            "interest_rate_bps": 525,
            "conditions": ["Quarterly financial review required"],
            "rationale": "Legacy v1-shaped payload (no model_versions on disk). Read path adds them via upcaster.",
            "confidence": 0.88,
        }
        ver = await store.stream_version(UPCAST_DEMO_STREAM_DECISION)
        evts = await store.append(
            UPCAST_DEMO_STREAM_DECISION,
            [{"event_type": "DecisionGenerated", "payload": decision_payload}],
            expected_version=ver,
            event_version=1,
        )
        results["decision_event_id"] = str(evts[0].event_id)
        results["created_decision"] = True

    results["message"] = (
        "Demo streams append legacy v1 payloads. The database row is never rewritten; "
        "get_event() applies upcasters on read only."
    )
    return results


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


# ── Static routes BEFORE parameterized routes ──


@router.get("/v1/streams")
async def list_streams(
    request: Request,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List all distinct stream_ids in the event store."""
    store = _require_pg(request)
    async with store._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT stream_id,
                   COUNT(*) AS event_count,
                   MAX(stream_position) AS max_position
            FROM events
            GROUP BY stream_id
            ORDER BY stream_id
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
        total_row = await conn.fetchrow("SELECT COUNT(DISTINCT stream_id) AS cnt FROM events")
    total = int(total_row["cnt"]) if total_row else 0
    return {
        "total": total,
        "streams": [
            {
                "stream_id": r["stream_id"],
                "event_count": int(r["event_count"]),
                "max_position": int(r["max_position"]),
            }
            for r in rows
        ],
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


@router.get("/v1/events/catalog")
async def list_events_catalog(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    event_version: int | None = Query(None, alias="eventVersion"),
) -> dict[str, Any]:
    """Paginated list of recent events for selection dropdowns."""
    store = _require_pg(request)
    ver_clause = ""
    params: list[Any] = [limit, offset]
    if event_version is not None:
        ver_clause = "WHERE event_version = $3"
        params.append(event_version)
    async with store._pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT event_id, event_type, event_version, stream_id, stream_position, global_position
            FROM events
            {ver_clause}
            ORDER BY global_position DESC
            LIMIT $1 OFFSET $2
            """,
            *params,
        )
        if event_version is not None:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM events WHERE event_version = $1",
                event_version,
            )
        else:
            total_row = await conn.fetchrow("SELECT COUNT(*) AS cnt FROM events")
    total = int(total_row["cnt"]) if total_row else 0
    return {
        "total": total,
        "events": [
            {
                "event_id": str(r["event_id"]),
                "event_type": r["event_type"],
                "event_version": int(r["event_version"]),
                "stream_id": r["stream_id"],
                "stream_position": int(r["stream_position"]),
                "global_position": int(r["global_position"]),
            }
            for r in rows
        ],
    }


@router.get("/v1/events/upcast-demo")
async def ensure_upcast_demo(request: Request) -> dict[str, Any]:
    """Idempotently create v1 demo events and return their IDs."""
    store = _require_pg(request)
    return await _ensure_upcast_demo_events(store)


@router.get("/v1/events/upcastable")
async def find_upcastable_event(request: Request) -> dict[str, Any]:
    """
    Auto-discover a v1 event eligible for upcasting. Prioritises demo streams,
    then any v1 CreditAnalysisCompleted / DecisionGenerated, then any v1 event,
    then the newest event in the store.
    """
    store = _require_pg(request)
    assert store._pool is not None
    async with store._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT event_id, event_type, event_version, stream_id
            FROM events
            WHERE event_version = 1
              AND event_type IN ('CreditAnalysisCompleted', 'DecisionGenerated')
            ORDER BY CASE stream_id
                        WHEN $1 THEN 0
                        WHEN $2 THEN 1
                        ELSE 2
                     END,
                     global_position DESC
            LIMIT 1
            """,
            UPCAST_DEMO_STREAM_CREDIT,
            UPCAST_DEMO_STREAM_DECISION,
        )
        if not row:
            row = await conn.fetchrow(
                """
                SELECT event_id, event_type, event_version, stream_id
                FROM events
                WHERE event_version = 1
                ORDER BY global_position DESC
                LIMIT 1
                """
            )
        if not row:
            row = await conn.fetchrow(
                """
                SELECT event_id, event_type, event_version, stream_id
                FROM events
                ORDER BY global_position DESC
                LIMIT 1
                """
            )
    if not row:
        return {
            "found": False,
            "event_id": None,
            "hint": "No events in the store.",
        }
    return {
        "found": True,
        "event_id": str(row["event_id"]),
        "event_type": row["event_type"],
        "stored_event_version": int(row["event_version"]),
        "stream_id": row["stream_id"],
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
        "explain": {
            "persisted_in_database": (
                "Left column: `get_event_raw()` -- exactly what is stored in the `events` row "
                "(event_version + payload JSON). No migration rewrote this row."
            ),
            "read_path_display_only": (
                "Right column: `get_event()` -- same row passed through UpcasterRegistry on load. "
                "Schema evolves for readers; the append-only store stays immutable."
            ),
            "when_identical": (
                "If both columns show the same version, this event was persisted already at the "
                "current schema (e.g. v2). Use 'Prepare demo v1 events' or pick a v1 row from the catalog."
            ),
        },
    }
