"""
Agent session management — run individual agents, concurrent runs,
crash simulation, and Gas Town recovery.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.api.services.pipeline import build_registry_client
from src.event_store import OptimisticConcurrencyError
from src.gas_town import reconstruct_agent_context
from src.schema.events import AgentType

router = APIRouter()


STAGE_TO_AGENT_TYPE = {
    "document": AgentType.DOCUMENT_PROCESSING.value,
    "credit": AgentType.CREDIT_ANALYSIS.value,
    "fraud": AgentType.FRAUD_DETECTION.value,
    "compliance": AgentType.COMPLIANCE.value,
    "decision": AgentType.DECISION_ORCHESTRATOR.value,
}


def _require_pg(request: Request) -> Any:
    store = request.app.state.store
    if getattr(store, "_pool", None) is None:
        raise HTTPException(503, "Agent endpoints require the PostgreSQL-backed API.")
    return store


def _ensure_submitted(loan_events: list) -> None:
    if not any(e.event_type == "ApplicationSubmitted" for e in loan_events):
        raise HTTPException(
            400,
            "Application has no ApplicationSubmitted event. Create it first via POST /v1/applications.",
        )


def _build_agent(stage: str, store: Any, llm_client: Any, *, crash: bool = False):
    """Instantiate the real LangGraph agent for a given stage."""
    from src.agents.compliance_agent import ComplianceAgent
    from src.agents.credit_analysis_agent import CreditAnalysisAgent
    from src.agents.decision_orchestrator_agent import DecisionOrchestratorAgent
    from src.agents.document_processing_agent import DocumentProcessingAgent
    from src.agents.fraud_detection_agent import FraudDetectionAgent

    reg = build_registry_client(store)
    agent_id = f"app-{stage}"
    at = STAGE_TO_AGENT_TYPE[stage]

    if stage == "document":
        return DocumentProcessingAgent(agent_id, at, store, reg, llm_client)
    if stage == "credit":
        return CreditAnalysisAgent(agent_id, at, store, reg, llm_client)
    if stage == "fraud":
        return FraudDetectionAgent(agent_id, at, store, reg, llm_client, crash_before_complete=crash)
    if stage == "compliance":
        return ComplianceAgent(agent_id, at, store, reg, llm_client)
    if stage == "decision":
        return DecisionOrchestratorAgent(agent_id, at, store, reg, llm_client)
    raise HTTPException(400, f"Unknown stage: {stage}")


def _session_events_json(events: list) -> list[dict[str, Any]]:
    return [
        {
            "stream_position": e.stream_position,
            "event_type": e.event_type,
            "payload": dict(e.payload) if isinstance(e.payload, dict) else e.payload,
            "recorded_at": str(e.recorded_at) if e.recorded_at else None,
        }
        for e in events
    ]


# ---------------------------------------------------------------------------
#  OCC-capturing store proxy
# ---------------------------------------------------------------------------

class _OccCapturingStore:
    """Thin proxy that captures OCC exceptions for reporting while delegating
    all other behaviour to the real store unchanged."""

    def __init__(self, real_store: Any):
        self._real = real_store
        self.occ_log: list[dict[str, Any]] = []

    async def append(self, stream_id, events, expected_version, **kw):
        try:
            return await self._real.append(stream_id, events, expected_version, **kw)
        except OptimisticConcurrencyError as exc:
            self.occ_log.append({
                "stream_id": exc.stream_id,
                "expected_version": exc.expected,
                "actual_version": exc.actual,
                "event_types": [ev.get("event_type", "?") for ev in events],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            raise

    def __getattr__(self, name: str):
        return getattr(self._real, name)


# ---------------------------------------------------------------------------
#  Run a single agent
# ---------------------------------------------------------------------------

class AgentRunBody(BaseModel):
    application_id: str
    stage: str = Field(..., description="One of: document, credit, fraud, compliance, decision")


@router.post("/v1/agents/run")
async def run_single_agent(request: Request, body: AgentRunBody) -> dict[str, Any]:
    """Run one real LangGraph agent against an application."""
    store = _require_pg(request)

    if body.stage not in STAGE_TO_AGENT_TYPE:
        raise HTTPException(400, f"Unknown stage '{body.stage}'. Must be one of {list(STAGE_TO_AGENT_TYPE)}")

    loan = await store.load_stream(f"loan-{body.application_id}")
    _ensure_submitted(loan)

    agent = _build_agent(body.stage, store, request.app.state.llm_client)
    t0 = time.time()
    try:
        await agent.process_application(body.application_id)
    except Exception as exc:
        return {
            "ok": False,
            "application_id": body.application_id,
            "stage": body.stage,
            "error": type(exc).__name__,
            "detail": str(exc)[:500],
            "session_id": agent.session_id,
            "duration_ms": int((time.time() - t0) * 1000),
        }

    session_stream = await store.load_stream(f"agent-{STAGE_TO_AGENT_TYPE[body.stage]}-{agent.session_id}")

    return {
        "ok": True,
        "application_id": body.application_id,
        "stage": body.stage,
        "session_id": agent.session_id,
        "session_stream": f"agent-{STAGE_TO_AGENT_TYPE[body.stage]}-{agent.session_id}",
        "duration_ms": int((time.time() - t0) * 1000),
        "session_events": _session_events_json(session_stream),
    }


# ---------------------------------------------------------------------------
#  Concurrent credit analysis (OCC demonstration)
# ---------------------------------------------------------------------------

class ConcurrentCreditBody(BaseModel):
    application_id: str


@router.post("/v1/agents/concurrent-credit")
async def concurrent_credit(request: Request, body: ConcurrentCreditBody) -> dict[str, Any]:
    """
    Run two CreditAnalysisAgents concurrently against the same application.
    One wins the append to credit-{id}; the other hits OCC (retries, sees winner's event, yields).
    Prerequisite stages (document) are run automatically if missing.
    """
    store = _require_pg(request)
    llm = request.app.state.llm_client
    app_id = body.application_id

    loan = await store.load_stream(f"loan-{app_id}")
    _ensure_submitted(loan)

    credit_events = await store.load_stream(f"credit-{app_id}")
    if any(e.event_type == "CreditAnalysisCompleted" for e in credit_events):
        raise HTTPException(
            409,
            f"credit-{app_id} already has a CreditAnalysisCompleted event. "
            "Pick an application that hasn't had credit analysis yet, or create a new one.",
        )

    if not any(e.event_type == "CreditAnalysisRequested" for e in loan):
        agent_doc = _build_agent("document", store, llm)
        await agent_doc.process_application(app_id)

    proxy = _OccCapturingStore(store)

    agent_a = _build_agent("credit", proxy, llm)
    agent_b = _build_agent("credit", proxy, llm)

    t0 = time.time()
    results = await asyncio.gather(
        _run_agent_safe(agent_a, app_id, "A"),
        _run_agent_safe(agent_b, app_id, "B"),
    )
    duration_ms = int((time.time() - t0) * 1000)

    credit_events = await store.load_stream(f"credit-{app_id}")
    completed = [e for e in credit_events if e.event_type == "CreditAnalysisCompleted"]
    winner_session = completed[0].payload.get("session_id") if completed else None

    for r in results:
        r["is_winner"] = r.get("session_id") == winner_session

    session_a_stream = await store.load_stream(
        f"agent-{AgentType.CREDIT_ANALYSIS.value}-{agent_a.session_id}"
    )
    session_b_stream = await store.load_stream(
        f"agent-{AgentType.CREDIT_ANALYSIS.value}-{agent_b.session_id}"
    )

    return {
        "application_id": app_id,
        "duration_ms": duration_ms,
        "results": results,
        "occ_events": proxy.occ_log,
        "credit_stream": _session_events_json(credit_events),
        "agent_a_session": _session_events_json(session_a_stream),
        "agent_b_session": _session_events_json(session_b_stream),
        "summary": _build_occ_summary(results, proxy.occ_log, winner_session),
    }


async def _run_agent_safe(agent, app_id: str, label: str) -> dict[str, Any]:
    try:
        await agent.process_application(app_id)
        return {
            "label": label,
            "session_id": agent.session_id,
            "ok": True,
            "error": None,
        }
    except Exception as exc:
        return {
            "label": label,
            "session_id": agent.session_id,
            "ok": False,
            "error": type(exc).__name__,
            "detail": str(exc)[:500],
        }


def _build_occ_summary(
    results: list[dict], occ_log: list[dict], winner_session: str | None
) -> str:
    winner = next((r for r in results if r.get("is_winner")), None)
    loser = next((r for r in results if not r.get("is_winner")), None)
    parts = []
    if winner:
        parts.append(
            f"Agent {winner['label']} (session {winner['session_id']}) won the race "
            f"and wrote CreditAnalysisCompleted to the credit stream."
        )
    if occ_log:
        for occ in occ_log:
            parts.append(
                f"OCC detected on {occ['stream_id']}: "
                f"expected version {occ['expected_version']}, "
                f"actual was {occ['actual_version']} "
                f"(event types: {', '.join(occ['event_types'])})."
            )
    if loser:
        if loser.get("ok"):
            parts.append(
                f"Agent {loser['label']} (session {loser['session_id']}) completed its session "
                f"but its CreditAnalysisCompleted was skipped — the winner's event already existed."
            )
        else:
            parts.append(
                f"Agent {loser['label']} (session {loser['session_id']}) "
                f"encountered {loser.get('error', 'an error')}: {loser.get('detail', '')}."
            )
    if not occ_log:
        parts.append(
            "No OCC exceptions were raised — one agent committed before the other reached the append. "
            "The domain-level idempotency check prevented the duplicate write."
        )
    return " ".join(parts)


# ---------------------------------------------------------------------------
#  Agent crash simulation + Gas Town recovery
# ---------------------------------------------------------------------------

class CrashSimBody(BaseModel):
    application_id: str


@router.post("/v1/agents/crash-simulation")
async def crash_simulation(request: Request, body: CrashSimBody) -> dict[str, Any]:
    """
    Run FraudDetectionAgent with crash_before_complete=True.
    The agent writes FraudScreeningInitiated + anomalies, then crashes
    before FraudScreeningCompleted. The base agent records AgentSessionFailed.
    Returns the partial work so you can then call /v1/agents/recover.
    """
    store = _require_pg(request)
    llm = request.app.state.llm_client
    app_id = body.application_id

    loan = await store.load_stream(f"loan-{app_id}")
    _ensure_submitted(loan)

    if not any(e.event_type == "CreditAnalysisRequested" for e in loan):
        agent_doc = _build_agent("document", store, llm)
        await agent_doc.process_application(app_id)

    agent = _build_agent("fraud", store, llm, crash=True)
    crash_error: str | None = None
    try:
        await agent.process_application(app_id)
    except Exception as exc:
        crash_error = f"{type(exc).__name__}: {exc}"

    session_id = agent.session_id
    at = AgentType.FRAUD_DETECTION.value
    session_stream = await store.load_stream(f"agent-{at}-{session_id}")
    fraud_stream = await store.load_stream(f"fraud-{app_id}")

    return {
        "application_id": app_id,
        "agent_type": at,
        "session_id": session_id,
        "crash_error": crash_error,
        "session_events": _session_events_json(session_stream),
        "fraud_stream_events": _session_events_json(fraud_stream),
    }


class RecoverBody(BaseModel):
    application_id: str
    session_id: str
    resume: bool = Field(
        default=True,
        description="After reconstructing context, run the fraud agent again with prior_session_id to resume.",
    )


@router.post("/v1/agents/recover")
async def recover_agent(request: Request, body: RecoverBody) -> dict[str, Any]:
    """
    Gas Town recovery: reconstruct_agent_context from the crashed session,
    then optionally resume the fraud agent with prior_session_id.
    """
    store = _require_pg(request)
    llm = request.app.state.llm_client
    at = AgentType.FRAUD_DETECTION.value

    ctx = await reconstruct_agent_context(store, at, body.session_id)
    out: dict[str, Any] = {
        "application_id": body.application_id,
        "crashed_session_id": body.session_id,
        "reconstructed_context": {
            "context_text": ctx.context_text,
            "last_event_position": ctx.last_event_position,
            "pending_work": ctx.pending_work,
            "session_health_status": ctx.session_health_status,
            "verbatim_tail": ctx.verbatim_tail,
        },
    }

    if body.resume:
        from src.agents.fraud_detection_agent import FraudDetectionAgent
        reg = build_registry_client(store)
        agent = FraudDetectionAgent(
            "app-fraud-resume", at, store, reg, llm, crash_before_complete=False,
        )
        resume_error: str | None = None
        try:
            await agent.process_application(body.application_id, prior_session_id=body.session_id)
        except Exception as exc:
            resume_error = f"{type(exc).__name__}: {exc}"

        resumed_session_stream = await store.load_stream(f"agent-{at}-{agent.session_id}")
        fraud_stream = await store.load_stream(f"fraud-{body.application_id}")

        out["resumed_session_id"] = agent.session_id
        out["resume_error"] = resume_error
        out["resumed_session_events"] = _session_events_json(resumed_session_stream)
        out["fraud_stream_after_resume"] = _session_events_json(fraud_stream)

    return out


# ---------------------------------------------------------------------------
#  View agent session
# ---------------------------------------------------------------------------

@router.get("/v1/agents/sessions/{stream_id:path}")
async def get_agent_session(request: Request, stream_id: str) -> dict[str, Any]:
    """Load all events from an agent session stream."""
    store = _require_pg(request)
    events = await store.load_stream(stream_id)
    if not events:
        raise HTTPException(404, f"No events found for stream '{stream_id}'")
    return {
        "stream_id": stream_id,
        "event_count": len(events),
        "events": _session_events_json(events),
    }
