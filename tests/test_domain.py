"""
Phase 2 — domain aggregates + handlers (InMemoryEventStore).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.domain.aggregates.agent_session import AgentSessionAggregate
from src.domain.aggregates.compliance_record import ComplianceRecordAggregate
from src.domain.aggregates.loan_application import LoanApplicationAggregate
from src.domain.errors import DomainError
from src.domain.handlers import (
    append_loan_event,
    handle_application_approved,
    handle_compliance_pipeline,
    handle_credit_analysis_completed,
    handle_decision_generated,
    handle_decision_requested,
    handle_fraud_pipeline,
    handle_human_review_completed,
    handle_open_credit_record,
    handle_start_agent_session,
    handle_submit_application,
)
from src.domain.streams import agent_stream_id, loan_stream_id
from src.event_store import InMemoryEventStore
from src.schema.events import (
    AgentType,
    ComplianceCheckRequested,
    CreditAnalysisRequested,
    CreditDecision,
    DecisionGenerated,
    FraudScreeningRequested,
    LoanPurpose,
    RiskTier,
    StoredEvent,
)


CORRELATION = "corr-test-001"
CAUSATION = "caus-test-001"


@pytest.fixture
async def store():
    return InMemoryEventStore()


async def _loan_pipeline_to_decision_ready(store: InMemoryEventStore, app_id: str, session_id: str) -> None:
    await handle_submit_application(
        store,
        application_id=app_id,
        applicant_id="COMP-1",
        requested_amount_usd=Decimal("250000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=60,
        submission_channel="portal",
        contact_email="a@b.co",
        contact_name="A",
        application_reference="REF-1",
        correlation_id=CORRELATION,
        causation_id=CAUSATION,
    )
    ev = CreditAnalysisRequested(
        application_id=app_id,
        requested_at=datetime.now(timezone.utc),
        requested_by="sys",
        priority="NORMAL",
    )
    await append_loan_event(store, app_id, ev.to_store_dict())
    await handle_open_credit_record(
        store, application_id=app_id, applicant_id="COMP-1",
        correlation_id=CORRELATION, causation_id=CAUSATION,
    )
    await handle_start_agent_session(
        store,
        agent_type=AgentType.CREDIT_ANALYSIS,
        session_id=session_id,
        agent_id="agent-credit",
        application_id=app_id,
        model_version="credit-v2",
        correlation_id=CORRELATION,
        causation_id=CAUSATION,
    )
    decision = CreditDecision(
        risk_tier=RiskTier.MEDIUM,
        recommended_limit_usd=Decimal("400000"),
        confidence=0.82,
        rationale="ok",
    )
    await handle_credit_analysis_completed(
        store,
        application_id=app_id,
        session_id=session_id,
        decision=decision,
        model_version="credit-v2",
        correlation_id=CORRELATION,
        causation_id=CAUSATION,
    )
    ev2 = FraudScreeningRequested(
        application_id=app_id,
        requested_at=datetime.now(timezone.utc),
        triggered_by_event_id="e1",
    )
    await append_loan_event(store, app_id, ev2.to_store_dict())
    await handle_fraud_pipeline(
        store, application_id=app_id, session_id=session_id,
        correlation_id=CORRELATION, causation_id=CAUSATION,
    )
    ev3 = ComplianceCheckRequested(
        application_id=app_id,
        requested_at=datetime.now(timezone.utc),
        triggered_by_event_id="e2",
        regulation_set_version="2026-Q1",
        rules_to_evaluate=["REG-001", "REG-002"],
    )
    await append_loan_event(store, app_id, ev3.to_store_dict())
    await handle_compliance_pipeline(
        store,
        application_id=app_id,
        session_id=session_id,
        rules_to_evaluate=["REG-001", "REG-002"],
        correlation_id=CORRELATION,
        causation_id=CAUSATION,
    )
    await handle_decision_requested(
        store, application_id=app_id, triggered_by_event_id="e3",
        correlation_id=CORRELATION, causation_id=CAUSATION,
    )


@pytest.mark.asyncio
async def test_stored_event_attributes(store: InMemoryEventStore):
    """Events returned by load_stream are StoredEvent with attribute access."""
    await handle_submit_application(
        store,
        application_id="APEX-SE-001",
        applicant_id="COMP-1",
        requested_amount_usd=Decimal("100000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=12,
        submission_channel="api",
        contact_email="a@b.co",
        contact_name="A",
        application_reference="REF-SE",
        correlation_id="corr-se-001",
        causation_id="caus-se-001",
    )
    events = await store.load_stream(loan_stream_id("APEX-SE-001"))
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, StoredEvent)
    assert ev.event_type == "ApplicationSubmitted"
    assert ev.stream_position == 0
    assert ev.payload["applicant_id"] == "COMP-1"
    assert ev.metadata["correlation_id"] == "corr-se-001"
    assert ev.metadata["causation_id"] == "caus-se-001"


@pytest.mark.asyncio
async def test_gas_town_first_event_must_be_agent_session_started(store: InMemoryEventStore):
    sid = "sess-bad"
    stream = agent_stream_id(AgentType.CREDIT_ANALYSIS.value, sid)
    from src.schema.events import AgentNodeExecuted

    bad = AgentNodeExecuted(
        session_id=sid,
        agent_type=AgentType.CREDIT_ANALYSIS,
        node_name="n",
        node_sequence=1,
        input_keys=[],
        output_keys=[],
        llm_called=False,
        duration_ms=1,
        executed_at=datetime.now(timezone.utc),
    )
    await store.append(stream, [bad.to_store_dict()], expected_version=await store.stream_version(stream))
    with pytest.raises(DomainError, match="Gas Town"):
        await AgentSessionAggregate.load(store, AgentType.CREDIT_ANALYSIS.value, sid)


@pytest.mark.asyncio
async def test_happy_path_decision_and_approval(store: InMemoryEventStore):
    app_id = "APEX-DOM-001"
    session_id = "sess-credit-001"
    orch_session = "sess-orch-001"
    await _loan_pipeline_to_decision_ready(store, app_id, session_id)

    await handle_decision_generated(
        store,
        application_id=app_id,
        orchestrator_session_id=orch_session,
        recommendation="APPROVE",
        confidence=0.85,
        contributing_sessions=[session_id],
        executive_summary="ok",
        correlation_id=CORRELATION,
    )

    await handle_application_approved(
        store,
        application_id=app_id,
        approved_amount_usd=Decimal("250000"),
        correlation_id=CORRELATION,
    )

    agg = await LoanApplicationAggregate.load(store, app_id)
    assert agg.state is not None
    assert agg.state.name == "APPROVED"


@pytest.mark.asyncio
async def test_confidence_floor_forces_refer(store: InMemoryEventStore):
    app_id = "APEX-DOM-002"
    session_id = "sess-credit-002"
    await _loan_pipeline_to_decision_ready(store, app_id, session_id)

    with pytest.raises(DomainError, match="0\\.6"):
        await handle_decision_generated(
            store,
            application_id=app_id,
            orchestrator_session_id="orch",
            recommendation="APPROVE",
            confidence=0.4,
            contributing_sessions=[session_id],
        )


@pytest.mark.asyncio
async def test_refer_decision_when_low_confidence(store: InMemoryEventStore):
    app_id = "APEX-DOM-003"
    session_id = "sess-credit-003"
    await _loan_pipeline_to_decision_ready(store, app_id, session_id)

    await handle_decision_generated(
        store,
        application_id=app_id,
        orchestrator_session_id="orch",
        recommendation="REFER",
        confidence=0.4,
        contributing_sessions=[session_id],
    )


@pytest.mark.asyncio
async def test_contributing_session_must_have_credit_completion(store: InMemoryEventStore):
    app_id = "APEX-DOM-004"
    session_id = "sess-credit-004"
    await _loan_pipeline_to_decision_ready(store, app_id, session_id)

    with pytest.raises(DomainError, match="Contributing session"):
        await handle_decision_generated(
            store,
            application_id=app_id,
            orchestrator_session_id="orch",
            recommendation="APPROVE",
            confidence=0.9,
            contributing_sessions=["fake-session"],
        )


@pytest.mark.asyncio
async def test_second_credit_requires_human_override(store: InMemoryEventStore):
    app_id = "APEX-DOM-005"
    session_id = "sess-credit-005"
    decision = CreditDecision(
        risk_tier=RiskTier.MEDIUM,
        recommended_limit_usd=Decimal("400000"),
        confidence=0.82,
        rationale="ok",
    )
    await _loan_pipeline_to_decision_ready(store, app_id, session_id)

    with pytest.raises(DomainError, match="second CreditAnalysisCompleted"):
        await handle_credit_analysis_completed(
            store,
            application_id=app_id,
            session_id=session_id,
            decision=decision,
            model_version="credit-v2",
        )

    await handle_decision_generated(
        store,
        application_id=app_id,
        orchestrator_session_id="orch-005",
        recommendation="REFER",
        confidence=0.5,
        contributing_sessions=[session_id],
    )

    await handle_human_review_completed(
        store,
        application_id=app_id,
        reviewer_id="u1",
        override=True,
        original_recommendation="REFER",
        final_decision="APPROVE",
        override_reason="re-run credit",
    )

    await handle_credit_analysis_completed(
        store,
        application_id=app_id,
        session_id=session_id,
        decision=decision,
        model_version="credit-v2",
    )


@pytest.mark.asyncio
async def test_compliance_blocks_approval_if_missing(store: InMemoryEventStore):
    app_id = "APEX-DOM-006"
    session_id = "sess-credit-006"
    await handle_submit_application(
        store,
        application_id=app_id,
        applicant_id="COMP-1",
        requested_amount_usd=Decimal("100000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=36,
        submission_channel="p",
        contact_email="x@y.z",
        contact_name="X",
        application_reference="R",
    )
    ev = DecisionGenerated(
        application_id=app_id,
        orchestrator_session_id="o",
        recommendation="APPROVE",
        confidence=0.9,
        executive_summary="x",
        contributing_sessions=[],
        generated_at=datetime.now(timezone.utc),
    )
    await append_loan_event(store, app_id, ev.to_store_dict())

    with pytest.raises(DomainError, match="Compliance"):
        await handle_application_approved(store, application_id=app_id, approved_amount_usd=Decimal("100000"))


@pytest.mark.asyncio
async def test_compliance_aggregate_tracks_rules(store: InMemoryEventStore):
    app_id = "APEX-DOM-007"
    session_id = "sess-007"
    await handle_compliance_pipeline(
        store,
        application_id=app_id,
        session_id=session_id,
        rules_to_evaluate=["R1"],
        correlation_id=CORRELATION,
    )
    c = await ComplianceRecordAggregate.load(store, app_id)
    assert "R1" in c.passed_rules


@pytest.mark.asyncio
async def test_aggregate_version_tracks_stream_position(store: InMemoryEventStore):
    """Aggregate.version reflects the latest stream version after load()."""
    app_id = "APEX-DOM-008"
    session_id = "sess-credit-008"
    await _loan_pipeline_to_decision_ready(store, app_id, session_id)
    agg = await LoanApplicationAggregate.load(store, app_id)
    loan_ver = await store.stream_version(loan_stream_id(app_id))
    assert agg.version == loan_ver
    assert agg.version > 0
