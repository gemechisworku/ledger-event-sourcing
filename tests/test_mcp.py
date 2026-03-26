"""Phase 5 — MCP tools + resources (InMemoryEventStore)."""
from __future__ import annotations

import json
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


async def _tool_structured(mcp, name: str, args: dict):
    """FastMCP 2.x: invoke tool and return structured JSON (tests only)."""
    r = await mcp._tool_manager.call_tool(name, args)
    return r.structured_content


@pytest.mark.asyncio
async def test_submit_application_tool():
    store = InMemoryEventStore()
    mcp = build_mcp_server(
        store,
        application_summary=ApplicationSummaryProjection(store),
        compliance_audit=ComplianceAuditProjection(store),
        agent_performance=AgentPerformanceLedgerProjection(store),
    )
    out = await _tool_structured(
        mcp,
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
    assert out.get("ok") is True
    assert out.get("stream_id") == "loan-MCP-001"


@pytest.mark.asyncio
async def test_submit_application_rejects_invalid_loan_purpose():
    store = InMemoryEventStore()
    mcp = build_mcp_server(
        store,
        application_summary=ApplicationSummaryProjection(store),
        compliance_audit=ComplianceAuditProjection(store),
        agent_performance=AgentPerformanceLedgerProjection(store),
    )
    out = await _tool_structured(
        mcp,
        "submit_application",
        {
            "application_id": "MCP-BAD-PURPOSE",
            "applicant_id": "A1",
            "requested_amount_usd": "250000",
            "loan_purpose": "E2E MCP lifecycle test",
            "loan_term_months": 36,
            "submission_channel": "mcp",
            "contact_email": "a@b.c",
            "contact_name": "Test",
            "application_reference": "REF-1",
        },
    )
    assert out.get("ok") is not True
    assert out.get("error_type") == "ValidationError"
    assert "loan_purpose must be one of:" in (out.get("message") or "")
    assert "application_reference" in (out.get("message") or "").lower()
    ctx = out.get("context") or {}
    assert ctx.get("field") == "loan_purpose"
    assert "working_capital" in (ctx.get("allowed_values") or [])


@pytest.mark.asyncio
async def test_realworld_style_submit_valid_and_invalid_loan_purpose():
    """
    Realistic CRM-style fields: valid loan_purpose succeeds; prose in loan_purpose returns ValidationError (no crash).
    """
    store = InMemoryEventStore()
    mcp = build_mcp_server(
        store,
        application_summary=ApplicationSummaryProjection(store),
        compliance_audit=ComplianceAuditProjection(store),
        agent_performance=AgentPerformanceLedgerProjection(store),
    )

    out_ok = await _tool_structured(
        mcp,
        "submit_application",
        {
            "application_id": "APEX-COMM-2026-004821",
            "applicant_id": "COMP-77341-B",
            "requested_amount_usd": "1250000",
            "loan_purpose": "expansion",
            "loan_term_months": 60,
            "submission_channel": "relationship_manager",
            "contact_email": "cfo@midwestfabrication.example.com",
            "contact_name": "Jordan Lee, CFO",
            "application_reference": "Working capital + equipment — Q1 2026 expansion (Denver facility)",
        },
    )
    assert out_ok.get("ok") is True
    assert out_ok.get("stream_id") == "loan-APEX-COMM-2026-004821"

    out_bad = await _tool_structured(
        mcp,
        "submit_application",
        {
            "application_id": "APEX-COMM-2026-004822",
            "applicant_id": "COMP-99102-A",
            "requested_amount_usd": "480000",
            "loan_purpose": "Purchase inventory and cover payroll for seasonal ramp-up",
            "loan_term_months": 36,
            "submission_channel": "online_banking",
            "contact_email": "treasurer@lakeside-retail.example.org",
            "contact_name": "Sam Rivera",
            "application_reference": "INV-2026-044 — seasonal WC line",
        },
    )
    assert out_bad.get("ok") is not True
    assert out_bad.get("error_type") == "ValidationError"
    assert "working_capital" in (out_bad.get("message") or "")


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
        return await _tool_structured(mcp, name, args)

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

    rr = await mcp._read_resource_mcp("ledger://applications/MCP-LIFE-1/compliance")
    assert rr[0].content
    comp = json.loads(rr[0].content)
    comp_blob = json.dumps(comp, default=str)
    assert comp.get("overall_verdict") == "CLEAR"
    assert comp.get("regulation_set_version") == "2026-Q1"
    assert "ComplianceRulePassed" in comp_blob
    assert "REG-001" in comp_blob

    r_app = await mcp._read_resource_mcp("ledger://applications/MCP-LIFE-1")
    text = r_app[0].content
    assert "MCP-LIFE-1" in text or "SUBMITTED" in text or "application_id" in text

    rh = await mcp._read_resource_mcp("ledger://ledger/health")
    health = json.loads(rh[0].content)
    assert "lags_ms" in health


@pytest.mark.asyncio
async def test_integrity_rate_limit():
    store = InMemoryEventStore()
    mcp = build_mcp_server(store)
    r1 = await _tool_structured(mcp, "run_integrity_check", {"entity_type": "loan", "entity_id": "RATE"})
    assert r1.get("ok") is True
    r2 = await _tool_structured(mcp, "run_integrity_check", {"entity_type": "loan", "entity_id": "RATE"})
    assert r2.get("error_type") == "PreconditionFailed"
