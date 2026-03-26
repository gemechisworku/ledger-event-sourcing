"""Compatibility shim — canonical command handlers: `src.commands.handlers`."""

from src.commands.handlers import (
    append_credit_event,
    append_fraud_event,
    append_loan_event,
    handle_application_approved,
    handle_compliance_pipeline,
    handle_credit_analysis_completed,
    handle_decision_generated,
    handle_decision_requested,
    handle_fraud_pipeline,
    handle_human_review_completed,
    handle_human_review_requested,
    handle_open_credit_record,
    handle_record_fraud_screening,
    handle_start_agent_session,
    handle_submit_application,
)

__all__ = [
    "append_credit_event",
    "append_fraud_event",
    "append_loan_event",
    "handle_application_approved",
    "handle_compliance_pipeline",
    "handle_credit_analysis_completed",
    "handle_decision_generated",
    "handle_decision_requested",
    "handle_fraud_pipeline",
    "handle_human_review_completed",
    "handle_human_review_requested",
    "handle_open_credit_record",
    "handle_record_fraud_screening",
    "handle_start_agent_session",
    "handle_submit_application",
]
