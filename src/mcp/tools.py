"""MCP tools (command side) — append-only stream mutations."""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from src.commands.handlers import (
    handle_compliance_pipeline,
    handle_credit_analysis_completed,
    handle_decision_generated,
    handle_human_review_completed,
    handle_record_fraud_screening,
    handle_start_agent_session,
    handle_submit_application,
)
from src.domain.errors import DomainError
from src.domain.streams import (
    agent_stream_id,
    credit_stream_id,
    fraud_stream_id,
    loan_stream_id,
)
from src.event_store import OptimisticConcurrencyError
from src.integrity.audit_chain import run_integrity_check
from src.models.events import AgentType, CreditDecision, LoanPurpose, RiskTier

_LOAN_PURPOSE_DOC = (
    "working_capital | equipment_financing | real_estate | expansion | "
    "refinancing | acquisition | bridge"
)


def _err(
    error_type: str,
    message: str,
    *,
    suggested_action: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {"error_type": error_type, "message": message}
    if suggested_action:
        out["suggested_action"] = suggested_action
    out.update(extra)
    return out


def _ok(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


_integrity_last: dict[tuple[str, str], float] = {}
_INTEGRITY_COOLDOWN_S = 60.0


def register_tools(mcp: FastMCP, store: Any) -> None:
    """Register the 8 command tools on the FastMCP app."""

    @mcp.tool(
        name="submit_application",
        description=(
            "Append ApplicationSubmitted to loan-{application_id}. "
            "Precondition: application_id must not already exist. "
            "Returns stream_id and new version. "
            "loan_purpose MUST be exactly one of these snake_case values (not a sentence): "
            f"{_LOAN_PURPOSE_DOC}. "
            "Use application_reference for free-text labels like 'E2E test'."
        ),
    )
    async def submit_application(
        application_id: str,
        applicant_id: str,
        requested_amount_usd: str,
        loan_purpose: str,
        loan_term_months: int,
        submission_channel: str,
        contact_email: str,
        contact_name: str,
        application_reference: str,
    ) -> dict[str, Any]:
        try:
            try:
                lp = LoanPurpose(loan_purpose)
            except ValueError:
                allowed = ", ".join(sorted(p.value for p in LoanPurpose))
                return _err(
                    "ValidationError",
                    f"loan_purpose must be one of: {allowed}. "
                    f"Received {loan_purpose!r}. Use application_reference for descriptive text.",
                )
            await handle_submit_application(
                store,
                application_id=application_id,
                applicant_id=applicant_id,
                requested_amount_usd=Decimal(requested_amount_usd),
                loan_purpose=lp,
                loan_term_months=loan_term_months,
                submission_channel=submission_channel,
                contact_email=contact_email,
                contact_name=contact_name,
                application_reference=application_reference,
            )
            v = await store.stream_version(loan_stream_id(application_id))
            return _ok(stream_id=loan_stream_id(application_id), new_stream_version=v)
        except DomainError as e:
            return _err("DomainError", str(e))
        except ValidationError as e:
            return _err("ValidationError", str(e))

    @mcp.tool(
        name="start_agent_session",
        description=(
            "Append AgentSessionStarted to agent-{agent_type}-{session_id}. "
            "Precondition: must run before other agent recording tools for that session. "
            "agent_type is e.g. credit_analysis, fraud_detection, compliance."
        ),
    )
    async def start_agent_session(
        agent_type: str,
        session_id: str,
        agent_id: str,
        application_id: str,
        model_version: str,
        context_source: str = "event_replay",
        context_token_count: int = 0,
    ) -> dict[str, Any]:
        try:
            at = AgentType(agent_type)
            await handle_start_agent_session(
                store,
                agent_type=at,
                session_id=session_id,
                agent_id=agent_id,
                application_id=application_id,
                model_version=model_version,
                context_source=context_source,
                context_token_count=context_token_count,
            )
            sid = agent_stream_id(agent_type, session_id)
            v = await store.stream_version(sid)
            return _ok(session_id=session_id, context_position=v, stream_id=sid)
        except DomainError as e:
            return _err("DomainError", str(e))
        except ValueError as e:
            return _err("ValidationError", str(e))

    @mcp.tool(
        name="record_credit_analysis",
        description=(
            "Append CreditAnalysisCompleted to credit-{application_id}. "
            "Requires active agent session (start_agent_session) with matching model_version. "
            "OCC on credit stream — on conflict reload and retry."
        ),
    )
    async def record_credit_analysis(
        application_id: str,
        session_id: str,
        model_version: str,
        risk_tier: str,
        recommended_limit_usd: str,
        confidence: float,
        rationale: str,
    ) -> dict[str, Any]:
        try:
            decision = CreditDecision(
                risk_tier=RiskTier(risk_tier.upper()),
                recommended_limit_usd=Decimal(recommended_limit_usd),
                confidence=confidence,
                rationale=rationale,
            )
            await handle_credit_analysis_completed(
                store,
                application_id=application_id,
                session_id=session_id,
                decision=decision,
                model_version=model_version,
            )
            v = await store.stream_version(credit_stream_id(application_id))
            return _ok(new_stream_version=v, stream_id=credit_stream_id(application_id))
        except DomainError as e:
            return _err("DomainError", str(e))
        except OptimisticConcurrencyError as e:
            return _err(
                "OptimisticConcurrencyError",
                str(e),
                stream_id=e.stream_id,
                expected_version=e.expected,
                actual_version=e.actual,
                suggested_action="reload_stream_and_retry",
            )

    @mcp.tool(
        name="record_fraud_screening",
        description=(
            "Append FraudScreeningInitiated + FraudScreeningCompleted on fraud-{application_id}. "
            "Requires start_agent_session for fraud_detection. fraud_score must be in [0.0, 1.0]."
        ),
    )
    async def record_fraud_screening(
        application_id: str,
        session_id: str,
        fraud_score: float,
        risk_level: str = "LOW",
        recommendation: str = "CLEAR",
    ) -> dict[str, Any]:
        try:
            await handle_record_fraud_screening(
                store,
                application_id=application_id,
                session_id=session_id,
                fraud_score=fraud_score,
                risk_level=risk_level,
                recommendation=recommendation,
            )
            v = await store.stream_version(fraud_stream_id(application_id))
            return _ok(new_stream_version=v, stream_id=fraud_stream_id(application_id))
        except DomainError as e:
            return _err("DomainError", str(e))
        except OptimisticConcurrencyError as e:
            return _err(
                "OptimisticConcurrencyError",
                str(e),
                stream_id=e.stream_id,
                expected_version=e.expected,
                actual_version=e.actual,
                suggested_action="reload_stream_and_retry",
            )

    @mcp.tool(
        name="record_compliance_check",
        description=(
            "Run compliance pipeline: ComplianceCheckInitiated + ComplianceRulePassed per rule + "
            "ComplianceCheckCompleted on compliance-{application_id}. "
            "Requires start_agent_session for compliance."
        ),
    )
    async def record_compliance_check(
        application_id: str,
        session_id: str,
        rules_to_evaluate: list[str],
        regulation_set_version: str = "2026-Q1",
    ) -> dict[str, Any]:
        try:
            await handle_compliance_pipeline(
                store,
                application_id=application_id,
                session_id=session_id,
                rules_to_evaluate=rules_to_evaluate,
                regulation_set_version=regulation_set_version,
            )
            return _ok(
                check_id=f"{application_id}-{session_id}",
                compliance_status="CLEAR",
                stream_id=f"compliance-{application_id}",
            )
        except DomainError as e:
            return _err("DomainError", str(e))
        except OptimisticConcurrencyError as e:
            return _err(
                "OptimisticConcurrencyError",
                str(e),
                suggested_action="reload_stream_and_retry",
            )

    @mcp.tool(
        name="generate_decision",
        description=(
            "Append DecisionGenerated to loan stream. "
            "Requires contributing_sessions to have CreditAnalysisCompleted for each session id. "
            "If confidence < 0.6, recommendation must be REFER (domain rule)."
        ),
    )
    async def generate_decision(
        application_id: str,
        orchestrator_session_id: str,
        recommendation: str,
        confidence: float,
        contributing_sessions: list[str],
        executive_summary: str = "MCP-generated decision",
    ) -> dict[str, Any]:
        try:
            await handle_decision_generated(
                store,
                application_id=application_id,
                orchestrator_session_id=orchestrator_session_id,
                recommendation=recommendation,
                confidence=confidence,
                contributing_sessions=contributing_sessions,
                executive_summary=executive_summary,
            )
            return _ok(decision_id=orchestrator_session_id, recommendation=recommendation.upper())
        except DomainError as e:
            return _err("DomainError", str(e))
        except OptimisticConcurrencyError as e:
            return _err("OptimisticConcurrencyError", str(e), suggested_action="reload_stream_and_retry")

    @mcp.tool(
        name="record_human_review",
        description=(
            "Append HumanReviewCompleted. Precondition: application in PENDING_HUMAN_REVIEW. "
            "If override=True, override_reason is required."
        ),
    )
    async def record_human_review(
        application_id: str,
        reviewer_id: str,
        override: bool,
        original_recommendation: str,
        final_decision: str,
        override_reason: str | None = None,
    ) -> dict[str, Any]:
        try:
            if override and not (override_reason and override_reason.strip()):
                return _err(
                    "PreconditionFailed",
                    "override_reason is required when override=True",
                )
            await handle_human_review_completed(
                store,
                application_id=application_id,
                reviewer_id=reviewer_id,
                override=override,
                original_recommendation=original_recommendation,
                final_decision=final_decision,
                override_reason=override_reason,
            )
            return _ok(final_decision=final_decision, application_state="updated")
        except DomainError as e:
            return _err("DomainError", str(e))

    @mcp.tool(
        name="run_integrity_check",
        description=(
            "Append AuditIntegrityCheckRun to audit-{entity_type}-{entity_id}. "
            "Rate limited to once per 60s per entity (PreconditionFailed if too fast)."
        ),
    )
    async def run_integrity_check_tool(entity_type: str, entity_id: str) -> dict[str, Any]:
        key = (entity_type, entity_id)
        now = time.monotonic()
        last = _integrity_last.get(key, 0.0)
        if now - last < _INTEGRITY_COOLDOWN_S and last > 0:
            return _err(
                "PreconditionFailed",
                f"Rate limit: wait {_INTEGRITY_COOLDOWN_S:.0f}s between checks for this entity",
            )
        try:
            r = await run_integrity_check(store, entity_type, entity_id)
            _integrity_last[key] = now
            return _ok(
                check_result={"events_verified": r.events_verified},
                chain_valid=r.chain_valid,
                tamper_detected=r.tamper_detected,
            )
        except Exception as e:
            return _err("DomainError", str(e))
