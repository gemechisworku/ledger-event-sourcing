"""Phase 5 — MCP tools + resources (InMemoryEventStore)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.event_store import InMemoryEventStore
from src.mcp_server import build_mcp_server
from src.projections import (
    AgentPerformanceLedgerProjection,
    ApplicationSummaryProjection,
    ComplianceAuditProjection,
    ProjectionDaemon,
)


def _structured(result):
    return result.structured_content


@pytest.mark.asyncio
async def test_submit_application_tool():
    store = InMemoryEventStore()
    mcp = build_mcp_server(
        store,
        application_summary=ApplicationSummaryProjection(store),
        compliance_audit=ComplianceAuditProjection(store),
        agent_performance=AgentPerformanceLedgerProjection(store),
    )
    r = await mcp.call_tool(
        "submit_application",
        {
            "application_id": "MCP-001",
            "applicant_id": "A1",
            "requested_amount_usd": "250000",
            "loan_purpose": "working_capital",
            "loan_term_months": 36,
            "submission_channel": "mcp",
            "contact_email": "a@b.c",
            "contact_name": "Test",
            "application_reference": "REF-1",
        },
    )
    out = _structured(r)
    assert out.get("ok") is True
    assert out.get("stream_id") == "loan-MCP-001"


@pytest.mark.asyncio
async def test_lifecycle_tools_only():
    """ApplicationSubmitted → credit → fraud → compliance → decision → human review (MCP tools only)."""
    store = InMemoryEventStore()
    projs = [
        ApplicationSummaryProjection(store),
        AgentPerformanceLedgerProjection(store),
        ComplianceAuditProjection(store),
    ]
    daemon = ProjectionDaemon(store, projs)
    mcp = build_mcp_server(
        store,
        daemon=daemon,
        application_summary=projs[0],
        agent_performance=projs[1],
        compliance_audit=projs[2],
    )
    app_id = "MCP-LIFE-1"

    async def call(name: str, args: dict):
        return _structured(await mcp.call_tool(name, args))

    assert (await call("submit_application", {"application_id": app_id, "applicant_id": "A1", "requested_amount_usd": "100000", "loan_purpose": "working_capital", "loan_term_months": 12, "submission_channel": "mcp", "contact_email": "x@y.z", "contact_name": "T", "application_reference": "R1"}))["ok"]

    assert (await call(
        "start_agent_session",
        {
            "agent_type": "credit_analysis",
            "session_id": "sess-credit",
            "agent_id": "ag-credit",
            "application_id": app_id,
            "model_version": "mv-1",
        },
    ))["ok"]

    assert (await call(
        "record_credit_analysis",
        {
            "application_id": app_id,
            "session_id": "sess-credit",
            "model_version": "mv-1",
            "risk_tier": "MEDIUM",
            "recommended_limit_usd": "90000",
            "confidence": 0.75,
            "rationale": "ok",
        },
    ))["ok"]

    assert (await call(
        "start_agent_session",
        {
            "agent_type": "fraud_detection",
            "session_id": "sess-fraud",
            "agent_id": "ag-fraud",
            "application_id": app_id,
            "model_version": "fraud-v1",
        },
    ))["ok"]

    assert (await call(
        "record_fraud_screening",
        {"application_id": app_id, "session_id": "sess-fraud", "fraud_score": 0.25},
    ))["ok"]

    assert (await call(
        "start_agent_session",
        {
            "agent_type": "compliance",
            "session_id": "sess-comp",
            "agent_id": "ag-comp",
            "application_id": app_id,
            "model_version": "comp-v1",
        },
    ))["ok"]

    assert (await call(
        "record_compliance_check",
        {
            "application_id": app_id,
            "session_id": "sess-comp",
            "rules_to_evaluate": ["REG-001"],
            "regulation_set_version": "2026-Q1",
        },
    ))["ok"]

    assert (await call(
        "generate_decision",
        {
            "application_id": app_id,
            "orchestrator_session_id": "orch-1",
            "recommendation": "REFER",
            "confidence": 0.55,
            "contributing_sessions": ["sess-credit"],
        },
    ))["ok"]

    assert (await call(
        "record_human_review",
        {
            "application_id": app_id,
            "reviewer_id": "LO-Sarah-Chen",
            "override": True,
            "original_recommendation": "REFER",
            "final_decision": "APPROVE",
            "override_reason": "Collateral sufficient",
        },
    ))["ok"]

    await daemon.process_batch()

    rr = await mcp.read_resource("ledger://applications/MCP-LIFE-1/compliance")
    assert rr.contents[0].content

    r_app = await mcp.read_resource("ledger://applications/MCP-LIFE-1")
    text = r_app.contents[0].content
    assert "MCP-LIFE-1" in text or "SUBMITTED" in text or "application_id" in text


@pytest.mark.asyncio
async def test_integrity_rate_limit():
    store = InMemoryEventStore()
    mcp = build_mcp_server(store)
    r1 = _structured(await mcp.call_tool("run_integrity_check", {"entity_type": "loan", "entity_id": "RATE"}))
    assert r1.get("ok") is True
    r2 = _structured(await mcp.call_tool("run_integrity_check", {"entity_type": "loan", "entity_id": "RATE"}))
    assert r2.get("error_type") == "PreconditionFailed"
