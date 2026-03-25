"""Phase 4 — projections + daemon (InMemoryEventStore)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.event_store import InMemoryEventStore
from src.projections import (
    AgentPerformanceLedgerProjection,
    ApplicationSummaryProjection,
    ComplianceAuditProjection,
    ProjectionDaemon,
)
from src.schema.events import (
    ApplicationSubmitted,
    ComplianceCheckCompleted,
    ComplianceVerdict,
    CreditAnalysisCompleted,
    CreditDecision,
    DecisionGenerated,
    LoanPurpose,
    RiskTier,
)


def _submitted(app_id: str) -> dict:
    return ApplicationSubmitted(
        application_id=app_id,
        applicant_id="A-1",
        requested_amount_usd=Decimal("100000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=12,
        submission_channel="web",
        contact_email="a@b.c",
        contact_name="A",
        submitted_at=datetime.now(timezone.utc),
        application_reference="R1",
    ).to_store_dict()


@pytest.mark.asyncio
async def test_daemon_updates_application_summary():
    store = InMemoryEventStore()
    app_id = "P4-APP-1"
    await store.append(f"loan-{app_id}", [_submitted(app_id)], expected_version=-1)

    projs = [
        ApplicationSummaryProjection(store),
        AgentPerformanceLedgerProjection(store),
        ComplianceAuditProjection(store),
    ]
    daemon = ProjectionDaemon(store, projs)
    n = await daemon.process_batch(batch_size=50)
    assert n >= 1

    row = await projs[0]._load_row(app_id)
    assert row.get("state") == "SUBMITTED"
    assert row.get("applicant_id") == "A-1"

    lags = await daemon.get_all_lags()
    assert all(v == 0 for v in lags.values())


@pytest.mark.asyncio
async def test_credit_and_decision_agent_performance():
    store = InMemoryEventStore()
    app_id = "P4-APP-2"
    await store.append(f"loan-{app_id}", [_submitted(app_id)], expected_version=-1)

    dec = CreditDecision(
        risk_tier=RiskTier.MEDIUM,
        recommended_limit_usd=Decimal("90000"),
        confidence=0.71,
        rationale="ok",
    )
    cac = CreditAnalysisCompleted(
        application_id=app_id,
        session_id="sess-1",
        decision=dec,
        model_version="m-v1",
        model_deployment_id="d1",
        input_data_hash="h",
        analysis_duration_ms=120,
        completed_at=datetime.now(timezone.utc),
    ).to_store_dict()
    await store.append(f"credit-{app_id}", [cac], expected_version=-1)

    dg = DecisionGenerated(
        application_id=app_id,
        orchestrator_session_id="orch-1",
        recommendation="APPROVE",
        confidence=0.9,
        executive_summary="x",
        generated_at=datetime.now(timezone.utc),
        model_versions={"credit": "m-v1"},
    ).to_store_dict()
    await store.append(f"loan-{app_id}", [dg], expected_version=0)

    perf = AgentPerformanceLedgerProjection(store)
    daemon = ProjectionDaemon(store, [ApplicationSummaryProjection(store), perf, ComplianceAuditProjection(store)])
    await daemon.process_batch()

    row = await perf._load("credit_analysis", "m-v1")
    assert row.get("analyses_completed", 0) >= 1


@pytest.mark.asyncio
async def test_compliance_projection_and_rebuild():
    store = InMemoryEventStore()
    app_id = "P4-APP-3"
    cc = ComplianceCheckCompleted(
        application_id=app_id,
        session_id="c1",
        rules_evaluated=2,
        rules_passed=2,
        rules_failed=0,
        rules_noted=0,
        has_hard_block=False,
        overall_verdict=ComplianceVerdict.CLEAR,
        completed_at=datetime.now(timezone.utc),
    ).to_store_dict()
    await store.append(f"compliance-{app_id}", [cc], expected_version=-1)

    comp = ComplianceAuditProjection(store)
    daemon = ProjectionDaemon(store, [comp])
    await daemon.process_batch()

    cur = await comp.get_current_compliance(app_id)
    assert cur.get("overall_verdict") == "CLEAR"

    await comp.rebuild_from_scratch()
    cur2 = await comp.get_current_compliance(app_id)
    assert cur2.get("overall_verdict") == "CLEAR"
