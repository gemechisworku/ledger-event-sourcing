"""
Command handlers — load → validate → emit → append.

Every handler follows the same disciplined pattern:
  1. Load the relevant aggregate(s) from the store
  2. Call guard methods on the aggregate for business-rule validation
  3. Construct domain event(s)
  4. Append via store.append() with expected_version from aggregate.version
  5. Thread correlation_id / causation_id into event metadata
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.domain.aggregates.agent_session import AgentSessionAggregate
from src.domain.aggregates.compliance_record import ComplianceRecordAggregate
from src.domain.aggregates.loan_application import LoanApplicationAggregate
from src.domain.errors import DomainError
from src.domain.streams import (
    agent_stream_id,
    compliance_stream_id,
    credit_stream_id,
    fraud_stream_id,
    loan_stream_id,
)
from src.schema.events import (
    AgentSessionStarted,
    AgentType,
    ApplicationApproved,
    ApplicationSubmitted,
    ComplianceCheckCompleted,
    ComplianceCheckInitiated,
    ComplianceRulePassed,
    ComplianceVerdict,
    CreditAnalysisCompleted,
    CreditDecision,
    CreditRecordOpened,
    DecisionGenerated,
    DecisionRequested,
    FraudScreeningCompleted,
    FraudScreeningInitiated,
    HumanReviewCompleted,
    HumanReviewRequested,
    LoanPurpose,
)


async def handle_submit_application(
    store: Any,
    *,
    application_id: str,
    applicant_id: str,
    requested_amount_usd: Decimal,
    loan_purpose: LoanPurpose,
    loan_term_months: int,
    submission_channel: str,
    contact_email: str,
    contact_name: str,
    application_reference: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_not_already_submitted()

    ev = ApplicationSubmitted(
        application_id=application_id,
        applicant_id=applicant_id,
        requested_amount_usd=requested_amount_usd,
        loan_purpose=loan_purpose,
        loan_term_months=loan_term_months,
        submission_channel=submission_channel,
        contact_email=contact_email,
        contact_name=contact_name,
        submitted_at=datetime.now(timezone.utc),
        application_reference=application_reference,
    )
    await store.append(
        loan_stream_id(application_id),
        [ev.to_store_dict()],
        expected_version=app.version,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_start_agent_session(
    store: Any,
    *,
    agent_type: AgentType,
    session_id: str,
    agent_id: str,
    application_id: str,
    model_version: str,
    langgraph_graph_version: str = "1.0",
    context_source: str = "event_replay",
    context_token_count: int = 0,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    agent = await AgentSessionAggregate.load(store, agent_type.value, session_id)
    agent.assert_not_already_started()

    ev = AgentSessionStarted(
        session_id=session_id,
        agent_type=agent_type,
        agent_id=agent_id,
        application_id=application_id,
        model_version=model_version,
        langgraph_graph_version=langgraph_graph_version,
        context_source=context_source,
        context_token_count=context_token_count,
        started_at=datetime.now(timezone.utc),
    )
    await store.append(
        agent.stream_id,
        [ev.to_store_dict()],
        expected_version=agent.version,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_credit_analysis_completed(
    store: Any,
    *,
    application_id: str,
    session_id: str,
    decision: CreditDecision,
    model_version: str,
    model_deployment_id: str = "prod",
    input_data_hash: str = "hash",
    analysis_duration_ms: int = 100,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_can_append_second_credit_analysis()

    agent = await AgentSessionAggregate.load(store, AgentType.CREDIT_ANALYSIS.value, session_id)
    agent.assert_context_loaded()
    agent.assert_model_version_current(model_version)

    ev = CreditAnalysisCompleted(
        application_id=application_id,
        session_id=session_id,
        decision=decision,
        model_version=model_version,
        model_deployment_id=model_deployment_id,
        input_data_hash=input_data_hash,
        analysis_duration_ms=analysis_duration_ms,
        completed_at=datetime.now(timezone.utc),
    )
    cs = credit_stream_id(application_id)
    await store.append(
        cs,
        [ev.to_store_dict()],
        expected_version=await store.stream_version(cs),
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_open_credit_record(
    store: Any,
    *,
    application_id: str,
    applicant_id: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    if app.state is None:
        raise DomainError("Cannot open credit record for non-existent application")

    cs = credit_stream_id(application_id)
    ev = CreditRecordOpened(
        application_id=application_id,
        applicant_id=applicant_id,
        opened_at=datetime.now(timezone.utc),
    )
    await store.append(
        cs,
        [ev.to_store_dict()],
        expected_version=await store.stream_version(cs),
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_fraud_pipeline(
    store: Any,
    *,
    application_id: str,
    session_id: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    if app.state is None:
        raise DomainError("Cannot run fraud pipeline for non-existent application")

    fs = fraud_stream_id(application_id)
    v = await store.stream_version(fs)
    await store.append(
        fs,
        [
            FraudScreeningInitiated(
                application_id=application_id,
                session_id=session_id,
                screening_model_version="fraud-v1",
                initiated_at=datetime.now(timezone.utc),
            ).to_store_dict()
        ],
        expected_version=v,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    v2 = await store.stream_version(fs)
    ev = FraudScreeningCompleted(
        application_id=application_id,
        session_id=session_id,
        fraud_score=0.1,
        risk_level="LOW",
        anomalies_found=0,
        recommendation="CLEAR",
        screening_model_version="fraud-v1",
        input_data_hash="fraud-hash",
        completed_at=datetime.now(timezone.utc),
    )
    await store.append(
        fs,
        [ev.to_store_dict()],
        expected_version=v2,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_record_fraud_screening(
    store: Any,
    *,
    application_id: str,
    session_id: str,
    fraud_score: float,
    risk_level: str = "LOW",
    anomalies_found: int = 0,
    recommendation: str = "CLEAR",
    screening_model_version: str = "fraud-v1",
    input_data_hash: str = "fraud-hash",
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    """Append fraud initiated + completed with caller-supplied score (MCP / tests)."""
    if not 0.0 <= fraud_score <= 1.0:
        raise DomainError("fraud_score must be between 0.0 and 1.0")
    app = await LoanApplicationAggregate.load(store, application_id)
    if app.state is None:
        raise DomainError("Cannot record fraud screening for non-existent application")

    fs = fraud_stream_id(application_id)
    v = await store.stream_version(fs)
    await store.append(
        fs,
        [
            FraudScreeningInitiated(
                application_id=application_id,
                session_id=session_id,
                screening_model_version=screening_model_version,
                initiated_at=datetime.now(timezone.utc),
            ).to_store_dict()
        ],
        expected_version=v,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    v2 = await store.stream_version(fs)
    ev = FraudScreeningCompleted(
        application_id=application_id,
        session_id=session_id,
        fraud_score=fraud_score,
        risk_level=risk_level,
        anomalies_found=anomalies_found,
        recommendation=recommendation,
        screening_model_version=screening_model_version,
        input_data_hash=input_data_hash,
        completed_at=datetime.now(timezone.utc),
    )
    await store.append(
        fs,
        [ev.to_store_dict()],
        expected_version=v2,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_compliance_pipeline(
    store: Any,
    *,
    application_id: str,
    session_id: str,
    rules_to_evaluate: list[str],
    regulation_set_version: str = "2026-Q1",
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    comp = await ComplianceRecordAggregate.load(store, application_id)

    cstream = compliance_stream_id(application_id)
    ev1 = ComplianceCheckInitiated(
        application_id=application_id,
        session_id=session_id,
        regulation_set_version=regulation_set_version,
        rules_to_evaluate=rules_to_evaluate,
        initiated_at=datetime.now(timezone.utc),
    )
    await store.append(
        cstream,
        [ev1.to_store_dict()],
        expected_version=comp.version,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    pos = await store.stream_version(cstream)
    passed: list[dict] = []
    for i, rid in enumerate(rules_to_evaluate):
        passed.append(
            ComplianceRulePassed(
                application_id=application_id,
                session_id=session_id,
                rule_id=rid,
                rule_name=f"Rule {rid}",
                rule_version="1",
                evidence_hash=f"h{i}",
                evaluation_notes="ok",
                evaluated_at=datetime.now(timezone.utc),
            ).to_store_dict()
        )
    await store.append(
        cstream,
        passed,
        expected_version=pos,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    pos2 = await store.stream_version(cstream)
    done = ComplianceCheckCompleted(
        application_id=application_id,
        session_id=session_id,
        rules_evaluated=len(rules_to_evaluate),
        rules_passed=len(rules_to_evaluate),
        rules_failed=0,
        rules_noted=0,
        has_hard_block=False,
        overall_verdict=ComplianceVerdict.CLEAR,
        completed_at=datetime.now(timezone.utc),
    )
    await store.append(
        cstream,
        [done.to_store_dict()],
        expected_version=pos2,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_decision_generated(
    store: Any,
    *,
    application_id: str,
    orchestrator_session_id: str,
    recommendation: str,
    confidence: float,
    contributing_sessions: list[str],
    executive_summary: str = "summary",
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_contributing_sessions_valid(contributing_sessions)
    app.assert_decision_confidence_valid(confidence, recommendation)

    ev = DecisionGenerated(
        application_id=application_id,
        orchestrator_session_id=orchestrator_session_id,
        recommendation=recommendation.upper(),
        confidence=confidence,
        executive_summary=executive_summary,
        contributing_sessions=contributing_sessions,
        generated_at=datetime.now(timezone.utc),
    )
    await store.append(
        loan_stream_id(application_id),
        [ev.to_store_dict()],
        expected_version=app.version,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_human_review_requested(
    store: Any,
    *,
    application_id: str,
    reason: str,
    decision_event_id: str,
    assigned_to: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    """Append HumanReviewRequested (e.g. mandatory review after orchestrator DECLINE)."""
    app = await LoanApplicationAggregate.load(store, application_id)

    ev = HumanReviewRequested(
        application_id=application_id,
        reason=reason,
        decision_event_id=decision_event_id,
        assigned_to=assigned_to,
        requested_at=datetime.now(timezone.utc),
    )
    await store.append(
        loan_stream_id(application_id),
        [ev.to_store_dict()],
        expected_version=app.version,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_human_review_completed(
    store: Any,
    *,
    application_id: str,
    reviewer_id: str,
    override: bool,
    original_recommendation: str,
    final_decision: str,
    override_reason: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_pending_human_review()

    ev = HumanReviewCompleted(
        application_id=application_id,
        reviewer_id=reviewer_id,
        override=override,
        original_recommendation=original_recommendation,
        final_decision=final_decision,
        override_reason=override_reason,
        reviewed_at=datetime.now(timezone.utc),
    )
    await store.append(
        loan_stream_id(application_id),
        [ev.to_store_dict()],
        expected_version=app.version,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_application_approved(
    store: Any,
    *,
    application_id: str,
    approved_amount_usd: Decimal,
    interest_rate_pct: float = 7.5,
    term_months: int = 60,
    conditions: list[str] | None = None,
    approved_by: str = "system",
    effective_date: str = "2026-04-01",
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_can_approve()

    comp = await ComplianceRecordAggregate.load(store, application_id)
    comp.assert_all_required_passed()

    ev = ApplicationApproved(
        application_id=application_id,
        approved_amount_usd=approved_amount_usd,
        interest_rate_pct=interest_rate_pct,
        term_months=term_months,
        conditions=list(conditions or []),
        approved_by=approved_by,
        effective_date=effective_date,
        approved_at=datetime.now(timezone.utc),
    )
    await store.append(
        loan_stream_id(application_id),
        [ev.to_store_dict()],
        expected_version=app.version,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def handle_decision_requested(
    store: Any,
    *,
    application_id: str,
    triggered_by_event_id: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_can_request_decision()

    ev = DecisionRequested(
        application_id=application_id,
        requested_at=datetime.now(timezone.utc),
        all_analyses_complete=True,
        triggered_by_event_id=triggered_by_event_id,
    )
    await store.append(
        loan_stream_id(application_id),
        [ev.to_store_dict()],
        expected_version=app.version,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


async def append_loan_event(store: Any, application_id: str, event_dict: dict) -> None:
    """Append a pre-built loan stream event (for tests / thin commands)."""
    ls = loan_stream_id(application_id)
    await store.append(ls, [event_dict], expected_version=await store.stream_version(ls))


async def append_credit_event(store: Any, application_id: str, event_dict: dict) -> None:
    cs = credit_stream_id(application_id)
    await store.append(cs, [event_dict], expected_version=await store.stream_version(cs))


async def append_fraud_event(store: Any, application_id: str, event_dict: dict) -> None:
    fs = fraud_stream_id(application_id)
    await store.append(fs, [event_dict], expected_version=await store.stream_version(fs))
