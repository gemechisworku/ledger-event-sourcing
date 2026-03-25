"""
Agent session management — run agents with live SSE logging,
dual parallel runs for OCC demonstration, interruptible runs for
Gas Town recovery.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.api.services.jobs import JobRegistry
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


def _build_agent(stage: str, store: Any, llm_client: Any):
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
        return FraudDetectionAgent(agent_id, at, store, reg, llm_client)
    if stage == "compliance":
        return ComplianceAgent(agent_id, at, store, reg, llm_client)
    if stage == "decision":
        return DecisionOrchestratorAgent(agent_id, at, store, reg, llm_client)
    raise HTTPException(400, f"Unknown stage: {stage}")


# ---------------------------------------------------------------------------
#  Logging store proxy — intercepts appends and pushes to SSE queue
# ---------------------------------------------------------------------------

class _LoggingStore:
    """Wraps the real store: every append pushes event details to an SSE queue."""

    def __init__(self, real_store: Any, queue: asyncio.Queue, label: str = ""):
        self._real = real_store
        self._queue = queue
        self._label = label

    async def append(self, stream_id, events, expected_version, **kw):
        try:
            result = await self._real.append(stream_id, events, expected_version, **kw)
            for idx, ev in enumerate(events):
                pos = result[idx] if isinstance(result, list) and idx < len(result) else None
                self._queue.put_nowait({
                    "type": "event_written",
                    "label": self._label,
                    "stream_id": stream_id,
                    "event_type": ev.get("event_type", "?"),
                    "stream_position": pos,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            return result
        except OptimisticConcurrencyError as exc:
            self._queue.put_nowait({
                "type": "occ_error",
                "label": self._label,
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
#  Run a single agent (streaming SSE)
# ---------------------------------------------------------------------------

class AgentRunBody(BaseModel):
    application_id: str
    stage: str = Field(..., description="One of: document, credit, fraud, compliance, decision")


@router.post("/v1/agents/run")
async def run_agent_streaming(request: Request, body: AgentRunBody) -> dict[str, Any]:
    """Start a single agent run. Returns a job_id for SSE streaming."""
    store = _require_pg(request)
    jobs: JobRegistry = request.app.state.jobs
    llm = request.app.state.llm_client

    if body.stage not in STAGE_TO_AGENT_TYPE:
        raise HTTPException(400, f"Unknown stage '{body.stage}'. Use: {list(STAGE_TO_AGENT_TYPE)}")

    loan = await store.load_stream(f"loan-{body.application_id}")
    if not any(e.event_type == "ApplicationSubmitted" for e in loan):
        raise HTTPException(400, "No ApplicationSubmitted — create the application first.")

    job_id = jobs.create()
    st = jobs.get(job_id)
    assert st is not None

    async def worker():
        proxy = _LoggingStore(store, st.queue, label="agent")
        agent = _build_agent(body.stage, proxy, llm)
        st.queue.put_nowait({
            "type": "progress",
            "message": f"Starting {body.stage} agent on {body.application_id}",
            "stage": body.stage,
            "application_id": body.application_id,
        })
        t0 = time.time()
        try:
            await agent.process_application(body.application_id)
            ms = int((time.time() - t0) * 1000)
            st.queue.put_nowait({
                "type": "complete",
                "message": f"{body.stage} agent completed in {ms}ms",
                "session_id": agent.session_id,
                "duration_ms": ms,
                "application_id": body.application_id,
            })
        except asyncio.CancelledError:
            ms = int((time.time() - t0) * 1000)
            st.queue.put_nowait({
                "type": "interrupted",
                "message": f"{body.stage} agent interrupted after {ms}ms",
                "session_id": agent.session_id,
                "duration_ms": ms,
                "application_id": body.application_id,
            })
        except Exception as exc:
            ms = int((time.time() - t0) * 1000)
            st.queue.put_nowait({
                "type": "error",
                "message": f"{type(exc).__name__}: {str(exc)[:500]}",
                "session_id": getattr(agent, "session_id", None),
                "duration_ms": ms,
                "application_id": body.application_id,
            })
        finally:
            st.done = True
            st.queue.put_nowait(None)

    task = asyncio.create_task(worker())
    st.task = task
    return {"job_id": job_id, "stream_url": f"/v1/jobs/{job_id}/stream"}


# ---------------------------------------------------------------------------
#  Run dual agents in parallel (same app + stage → OCC)
# ---------------------------------------------------------------------------

class DualRunBody(BaseModel):
    application_id: str
    stage: str = Field(..., description="Stage to run in parallel (e.g. credit, fraud)")


@router.post("/v1/agents/run-dual")
async def run_dual_agents(request: Request, body: DualRunBody) -> dict[str, Any]:
    """
    Run two instances of the same agent on the same application concurrently.
    Both stream logs to the same SSE job. OCC events are captured and streamed.
    """
    store = _require_pg(request)
    jobs: JobRegistry = request.app.state.jobs
    llm = request.app.state.llm_client

    if body.stage not in STAGE_TO_AGENT_TYPE:
        raise HTTPException(400, f"Unknown stage '{body.stage}'. Use: {list(STAGE_TO_AGENT_TYPE)}")

    loan = await store.load_stream(f"loan-{body.application_id}")
    if not any(e.event_type == "ApplicationSubmitted" for e in loan):
        raise HTTPException(400, "No ApplicationSubmitted — create the application first.")

    job_id = jobs.create()
    st = jobs.get(job_id)
    assert st is not None

    async def run_one(label: str):
        proxy = _LoggingStore(store, st.queue, label=label)
        agent = _build_agent(body.stage, proxy, llm)
        st.queue.put_nowait({
            "type": "progress",
            "label": label,
            "message": f"[{label}] Starting {body.stage} agent",
            "stage": body.stage,
            "application_id": body.application_id,
        })
        t0 = time.time()
        try:
            await agent.process_application(body.application_id)
            ms = int((time.time() - t0) * 1000)
            st.queue.put_nowait({
                "type": "agent_done",
                "label": label,
                "ok": True,
                "message": f"[{label}] {body.stage} agent completed in {ms}ms",
                "session_id": agent.session_id,
                "duration_ms": ms,
            })
        except Exception as exc:
            ms = int((time.time() - t0) * 1000)
            st.queue.put_nowait({
                "type": "agent_done",
                "label": label,
                "ok": False,
                "message": f"[{label}] {type(exc).__name__}: {str(exc)[:300]}",
                "session_id": getattr(agent, "session_id", None),
                "duration_ms": ms,
                "error": type(exc).__name__,
            })

    async def worker():
        st.queue.put_nowait({
            "type": "progress",
            "message": f"Running two {body.stage} agents in parallel on {body.application_id}",
            "application_id": body.application_id,
        })
        await asyncio.gather(run_one("Agent-A"), run_one("Agent-B"))
        st.queue.put_nowait({
            "type": "complete",
            "message": "Both agents finished. Check logs for OCC events.",
            "application_id": body.application_id,
        })
        st.done = True
        st.queue.put_nowait(None)

    task = asyncio.create_task(worker())
    st.task = task
    return {"job_id": job_id, "stream_url": f"/v1/jobs/{job_id}/stream"}


# ---------------------------------------------------------------------------
#  Interrupt a running agent
# ---------------------------------------------------------------------------

@router.post("/v1/agents/interrupt/{job_id}")
async def interrupt_agent(request: Request, job_id: str) -> dict[str, Any]:
    """Cancel a running agent task. Events written before cancellation remain in the store."""
    jobs: JobRegistry = request.app.state.jobs
    cancelled = jobs.cancel(job_id)
    if not cancelled:
        raise HTTPException(404, "Job not found or already finished")
    return {"job_id": job_id, "interrupted": True}


# ---------------------------------------------------------------------------
#  Gas Town: reconstruct agent context
# ---------------------------------------------------------------------------

class RecoverBody(BaseModel):
    session_id: str
    agent_type: str = Field(default="", description="Agent type value, e.g. credit_analysis")


@router.post("/v1/agents/recover")
async def recover_agent(request: Request, body: RecoverBody) -> dict[str, Any]:
    """Reconstruct agent context from the ledger after an interrupted session."""
    store = _require_pg(request)
    at = body.agent_type or AgentType.CREDIT_ANALYSIS.value
    ctx = await reconstruct_agent_context(store, at, body.session_id)
    return {
        "session_id": body.session_id,
        "agent_type": at,
        "reconstructed_context": {
            "context_text": ctx.context_text,
            "last_event_position": ctx.last_event_position,
            "pending_work": ctx.pending_work,
            "session_health_status": ctx.session_health_status,
            "verbatim_tail": ctx.verbatim_tail,
        },
    }


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
        "events": [
            {
                "stream_position": e.stream_position,
                "event_type": e.event_type,
                "payload": dict(e.payload) if isinstance(e.payload, dict) else e.payload,
                "recorded_at": str(e.recorded_at) if e.recorded_at else None,
            }
            for e in events
        ],
    }
