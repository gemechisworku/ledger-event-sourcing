"""Application CRUD-style endpoints backed by event streams."""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Request

from src.api.schemas import ApplicationCreate, ApplicationListItem, ApplicationListResponse, ApplicationResponse
from src.domain.errors import DomainError
from src.domain.handlers import handle_submit_application
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
