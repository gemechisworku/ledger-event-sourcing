"""
Maps internal ApplicationState values to the evaluation rubric's canonical phase names.

Rubric path (narrative):
  Submitted → AwaitingAnalysis → AnalysisComplete → ComplianceReview → PendingDecision
  → ApprovedPendingHuman / DeclinedPendingHuman → FinalApproved / FinalDeclined
"""
from __future__ import annotations

from src.models.events import ApplicationState

_RUBRIC_BY_STATE: dict[ApplicationState, str] = {
    ApplicationState.SUBMITTED: "Submitted",
    ApplicationState.DOCUMENTS_PENDING: "Submitted",
    ApplicationState.DOCUMENTS_UPLOADED: "Submitted",
    ApplicationState.DOCUMENTS_PROCESSED: "Submitted",
    ApplicationState.CREDIT_ANALYSIS_REQUESTED: "AwaitingAnalysis",
    ApplicationState.CREDIT_ANALYSIS_COMPLETE: "AnalysisComplete",
    ApplicationState.FRAUD_SCREENING_REQUESTED: "AnalysisComplete",
    ApplicationState.FRAUD_SCREENING_COMPLETE: "AnalysisComplete",
    ApplicationState.COMPLIANCE_CHECK_REQUESTED: "ComplianceReview",
    ApplicationState.COMPLIANCE_CHECK_COMPLETE: "ComplianceReview",
    ApplicationState.PENDING_DECISION: "PendingDecision",
    ApplicationState.PENDING_HUMAN_REVIEW: "ApprovedPendingHuman",
    ApplicationState.DECLINED: "FinalDeclined",
    ApplicationState.DECLINED_COMPLIANCE: "FinalDeclined",
    ApplicationState.APPROVED: "FinalApproved",
    ApplicationState.REFERRED: "PendingDecision",
}


def to_rubric_phase(state: ApplicationState | None) -> str:
    """Human-readable rubric phase; use for reporting / grading cross-walk."""
    if state is None:
        return "New"
    return _RUBRIC_BY_STATE.get(state, state.value)
