"""
Command handlers — load → validate → emit → append.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ledger.domain.aggregates.agent_session import AgentSessionAggregate
from ledger.domain.aggregates.compliance_record import ComplianceRecordAggregate
from ledger.domain.aggregates.loan_application import LoanApplicationAggregate
from ledger.domain.errors import DomainError
from ledger.domain.streams import (
    agent_stream_id,
    compliance_stream_id,
    credit_stream_id,
    fraud_stream_id,
    loan_stream_id,
)
from ledger.schema.events import (
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
    LoanPurpose,
)


def _override_allows_second_credit_analysis(loan_events: list[dict], credit_events: list[dict]) -> bool:
    """Rule 3: second credit completion requires HumanReviewCompleted(override=True) after first completion."""
    completions = sorted(
        [e for e in credit_events if e["event_type"] == "CreditAnalysisCompleted"],
        key=lambda e: e["global_position"],
    )
    if len(completions) < 1:
        return True
    first_pos = completions[0]["global_position"]
    for e in loan_events:
        if e["event_type"] != "HumanReviewCompleted":
            continue
        if not e.get("payload", {}).get("override"):
            continue
        if e["global_position"] > first_pos:
            return True
    return False


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
) -> None:
    sid = loan_stream_id(application_id)
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
    await store.append(sid, [ev.to_store_dict()], expected_version=await store.stream_version(sid))


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
) -> None:
    stream = agent_stream_id(agent_type.value, session_id)
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
    await store.append(stream, [ev.to_store_dict()], expected_version=await store.stream_version(stream))


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
) -> None:
    loan_events = await store.load_stream(loan_stream_id(application_id))
    credit_events = await store.load_stream(credit_stream_id(application_id))
    if len([e for e in credit_events if e["event_type"] == "CreditAnalysisCompleted"]) >= 1:
        if not _override_allows_second_credit_analysis(loan_events, credit_events):
            raise DomainError(
                "Second CreditAnalysisCompleted requires HumanReviewCompleted with override after first credit"
            )

    agent_type = AgentType.CREDIT_ANALYSIS.value
    agent = await AgentSessionAggregate.load(store, agent_type, session_id)
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
    await store.append(cs, [ev.to_store_dict()], expected_version=await store.stream_version(cs))


async def handle_open_credit_record(
    store: Any,
    *,
    application_id: str,
    applicant_id: str,
) -> None:
    cs = credit_stream_id(application_id)
    ev = CreditRecordOpened(
        application_id=application_id,
        applicant_id=applicant_id,
        opened_at=datetime.now(timezone.utc),
    )
    await store.append(cs, [ev.to_store_dict()], expected_version=await store.stream_version(cs))


async def handle_fraud_pipeline(
    store: Any,
    *,
    application_id: str,
    session_id: str,
) -> None:
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
    await store.append(fs, [ev.to_store_dict()], expected_version=v2)


async def handle_compliance_pipeline(
    store: Any,
    *,
    application_id: str,
    session_id: str,
    rules_to_evaluate: list[str],
    regulation_set_version: str = "2026-Q1",
) -> None:
    cstream = compliance_stream_id(application_id)
    ev1 = ComplianceCheckInitiated(
        application_id=application_id,
        session_id=session_id,
        regulation_set_version=regulation_set_version,
        rules_to_evaluate=rules_to_evaluate,
        initiated_at=datetime.now(timezone.utc),
    )
    await store.append(cstream, [ev1.to_store_dict()], expected_version=await store.stream_version(cstream))
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
    await store.append(cstream, passed, expected_version=pos)
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
    await store.append(cstream, [done.to_store_dict()], expected_version=pos2)


async def handle_decision_generated(
    store: Any,
    *,
    application_id: str,
    orchestrator_session_id: str,
    recommendation: str,
    confidence: float,
    contributing_sessions: list[str],
    executive_summary: str = "summary",
) -> None:
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_contributing_sessions_valid(contributing_sessions)

    rec = recommendation.upper()
    if confidence < 0.6 and rec != "REFER":
        raise DomainError("confidence < 0.6 requires recommendation REFER")

    ev = DecisionGenerated(
        application_id=application_id,
        orchestrator_session_id=orchestrator_session_id,
        recommendation=rec,
        confidence=confidence,
        executive_summary=executive_summary,
        contributing_sessions=contributing_sessions,
        generated_at=datetime.now(timezone.utc),
    )
    ls = loan_stream_id(application_id)
    await store.append(ls, [ev.to_store_dict()], expected_version=await store.stream_version(ls))


async def handle_human_review_completed(
    store: Any,
    *,
    application_id: str,
    reviewer_id: str,
    override: bool,
    original_recommendation: str,
    final_decision: str,
    override_reason: str | None,
) -> None:
    ev = HumanReviewCompleted(
        application_id=application_id,
        reviewer_id=reviewer_id,
        override=override,
        original_recommendation=original_recommendation,
        final_decision=final_decision,
        override_reason=override_reason,
        reviewed_at=datetime.now(timezone.utc),
    )
    ls = loan_stream_id(application_id)
    await store.append(ls, [ev.to_store_dict()], expected_version=await store.stream_version(ls))


async def handle_application_approved(
    store: Any,
    *,
    application_id: str,
    approved_amount_usd: Decimal,
    interest_rate_pct: float = 7.5,
    term_months: int = 60,
    approved_by: str = "system",
    effective_date: str = "2026-04-01",
) -> None:
    comp = await ComplianceRecordAggregate.load(store, application_id)
    comp.assert_all_required_passed()

    ev = ApplicationApproved(
        application_id=application_id,
        approved_amount_usd=approved_amount_usd,
        interest_rate_pct=interest_rate_pct,
        term_months=term_months,
        approved_by=approved_by,
        effective_date=effective_date,
        approved_at=datetime.now(timezone.utc),
    )
    ls = loan_stream_id(application_id)
    await store.append(ls, [ev.to_store_dict()], expected_version=await store.stream_version(ls))


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


async def handle_decision_requested(
    store: Any,
    *,
    application_id: str,
    triggered_by_event_id: str,
) -> None:
    ev = DecisionRequested(
        application_id=application_id,
        requested_at=datetime.now(timezone.utc),
        all_analyses_complete=True,
        triggered_by_event_id=triggered_by_event_id,
    )
    ls = loan_stream_id(application_id)
    await store.append(ls, [ev.to_store_dict()], expected_version=await store.stream_version(ls))
