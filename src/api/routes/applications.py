"""Application CRUD-style endpoints backed by event streams."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationListResponse,
    ApplicationResponse,
    DecisionHistoryEvent,
    DecisionHistoryResponse,
)
from src.domain.errors import DomainError
from src.domain.handlers import handle_submit_application
from src.integrity.audit_chain import run_integrity_check
from src.projections import ComplianceAuditProjection
from src.schema.events import LoanPurpose

router = APIRouter()


@router.get("/v1/applications", response_model=ApplicationListResponse)
async def list_applications(
    request: Request,
    limit: int = 200,
    offset: int = 0,
) -> ApplicationListResponse:
    """List applications from `projection_application_summary` (requires PostgreSQL)."""
    store = request.app.state.store
    pool = getattr(store, "_pool", None) or getattr(store, "pool", None)
    if pool is None:
        return ApplicationListResponse(
            applications=[],
            note="Projection listing requires PostgreSQL; in-memory store has no application index.",
        )
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pas.application_id, pas.state, pas.applicant_id, pas.requested_amount_usd,
                   pas.decision, pas.risk_tier, pas.compliance_status, pas.fraud_score,
                   pas.last_event_type, pas.last_event_at, pas.updated_at,
                   COALESCE(es.current_version, -1) AS stream_version
            FROM projection_application_summary pas
            LEFT JOIN event_streams es ON es.stream_id = 'loan-' || pas.application_id
            ORDER BY COALESCE(pas.last_event_at, pas.updated_at) DESC NULLS LAST
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    items: list[ApplicationListItem] = []
    for r in rows:
        ra = r["requested_amount_usd"]
        items.append(
            ApplicationListItem(
                application_id=r["application_id"],
                state=r["state"],
                applicant_id=r["applicant_id"],
                requested_amount_usd=str(ra) if ra is not None else None,
                decision=r["decision"],
                risk_tier=r["risk_tier"],
                compliance_status=r["compliance_status"],
                fraud_score=float(r["fraud_score"]) if r["fraud_score"] is not None else None,
                last_event_type=r["last_event_type"],
                last_event_at=r["last_event_at"].isoformat() if r["last_event_at"] else None,
                updated_at=r["updated_at"].isoformat() if r["updated_at"] else None,
                stream_version=int(r["stream_version"]),
            )
        )
    return ApplicationListResponse(applications=items)


@router.post("/v1/applications", response_model=ApplicationResponse)
async def create_application(body: ApplicationCreate, request: Request) -> ApplicationResponse:
    store = request.app.state.store
    try:
        await handle_submit_application(
            store,
            application_id=body.application_id,
            applicant_id=body.applicant_id,
            requested_amount_usd=body.requested_amount_usd,
            loan_purpose=LoanPurpose(body.loan_purpose),
            loan_term_months=body.loan_term_months,
            submission_channel=body.submission_channel,
            contact_email=body.contact_email,
            contact_name=body.contact_name,
            application_reference=body.application_reference,
        )
    except DomainError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    v = await store.stream_version(f"loan-{body.application_id}")
    return ApplicationResponse(
        application_id=body.application_id,
        stream_id=f"loan-{body.application_id}",
        stream_version=v,
    )


@router.get("/v1/applications/{application_id}")
async def get_application(application_id: str, request: Request) -> dict:
    store = request.app.state.store
    loan = await store.load_stream(f"loan-{application_id}")
    if not loan:
        raise HTTPException(status_code=404, detail="Application not found")
    events = []
    for e in loan:
        payload = e.payload if isinstance(e.payload, dict) else dict(e.payload or {})
        events.append(
            {
                "event_type": e.event_type,
                "stream_position": e.stream_position,
                "payload": json.loads(json.dumps(payload, default=str)),
            }
        )
    return {
        "application_id": application_id,
        "stream_id": f"loan-{application_id}",
        "event_count": len(events),
        "events": events,
    }


@router.get("/v1/applications/{application_id}/decision-history", response_model=DecisionHistoryResponse)
async def get_decision_history(application_id: str, request: Request) -> DecisionHistoryResponse:
    """Complete decision history across all streams for one application."""
    store = request.app.state.store

    stream_prefixes = ["loan", "credit", "fraud", "compliance", "docpkg"]
    all_events: list[DecisionHistoryEvent] = []
    streams_queried: list[str] = []

    for prefix in stream_prefixes:
        sid = f"{prefix}-{application_id}"
        streams_queried.append(sid)
        evs = await store.load_stream(sid)
        for e in evs:
            payload = e.payload if isinstance(e.payload, dict) else dict(e.payload or {})
            all_events.append(
                DecisionHistoryEvent(
                    stream_id=sid,
                    event_type=e.event_type,
                    stream_position=e.stream_position,
                    global_position=getattr(e, "global_position", None),
                    recorded_at=e.recorded_at.isoformat() if e.recorded_at else None,
                    payload=json.loads(json.dumps(payload, default=str)),
                )
            )

    pool = getattr(store, "_pool", None) or getattr(store, "pool", None)
    if pool is not None:
        async with pool.acquire() as conn:
            agent_rows = await conn.fetch(
                "SELECT stream_id FROM event_streams WHERE stream_id LIKE 'agent-%' AND stream_id LIKE $1",
                f"%-{application_id}%",
            )
        for row in agent_rows:
            sid = row["stream_id"]
            if sid not in streams_queried:
                streams_queried.append(sid)
                evs = await store.load_stream(sid)
                for e in evs:
                    payload = e.payload if isinstance(e.payload, dict) else dict(e.payload or {})
                    all_events.append(
                        DecisionHistoryEvent(
                            stream_id=sid,
                            event_type=e.event_type,
                            stream_position=e.stream_position,
                            global_position=getattr(e, "global_position", None),
                            recorded_at=e.recorded_at.isoformat() if e.recorded_at else None,
                            payload=json.loads(json.dumps(payload, default=str)),
                        )
                    )

    all_events.sort(key=lambda e: e.global_position if e.global_position is not None else 0)

    integrity = None
    try:
        r = await run_integrity_check(store, "loan", application_id)
        integrity = {
            "chain_valid": r.chain_valid,
            "tamper_detected": r.tamper_detected,
            "events_verified": r.events_verified,
        }
    except Exception:
        pass

    if not all_events:
        raise HTTPException(status_code=404, detail="No events found for this application")

    return DecisionHistoryResponse(
        application_id=application_id,
        total_events=len(all_events),
        streams_queried=streams_queried,
        events=all_events,
        integrity=integrity,
    )


@router.get("/v1/applications/{application_id}/compliance")
async def get_compliance(
    application_id: str,
    request: Request,
    as_of: str | None = Query(None, description="ISO-8601 timestamp for temporal query"),
) -> dict:
    """Current or temporal compliance state for an application."""
    store = request.app.state.store
    proj = ComplianceAuditProjection(store)
    if as_of:
        ts = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        result = await proj.get_compliance_at(application_id, ts)
    else:
        result = await proj.get_current_compliance(application_id)
    return json.loads(json.dumps(result, default=str))


@router.get("/v1/applications/{application_id}/compliance/compare")
async def compliance_compare(
    application_id: str,
    request: Request,
    as_of: str = Query(..., description="ISO-8601 timestamp for temporal comparison"),
) -> dict:
    """Side-by-side: current compliance vs compliance at a past point in time."""
    from src.domain.streams import compliance_stream_id as _csid

    store = request.app.state.store
    proj = ComplianceAuditProjection(store)

    ts = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    current = await proj.get_current_compliance(application_id)
    historical = await proj.get_compliance_at(application_id, ts)

    stream = await store.load_stream(_csid(application_id))
    timeline = [
        {
            "event_type": e.event_type,
            "stream_position": e.stream_position,
            "recorded_at": str(e.recorded_at) if e.recorded_at else None,
        }
        for e in stream
    ]

    return json.loads(json.dumps({
        "application_id": application_id,
        "as_of": as_of,
        "current": current,
        "as_of_projection": historical,
        "compliance_event_timeline": timeline,
    }, default=str))
