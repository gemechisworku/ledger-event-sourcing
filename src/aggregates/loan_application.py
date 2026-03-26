"""
LoanApplication aggregate — stream `loan-{application_id}`.
Replays loan, credit, fraud, and compliance streams for a coherent application state.

Uses per-event dispatch: _apply delegates to _on_{EventType} methods.

Rubric phase names (Submitted → AwaitingAnalysis → …) map to ApplicationState via
``src.domain.rubric_states.to_rubric_phase`` for grading cross-walk.
"""

from __future__ import annotations

from typing import Any

from src.domain.errors import DomainError
from src.domain.streams import compliance_stream_id, credit_stream_id, fraud_stream_id, loan_stream_id
from src.models.events import ApplicationState, StoredEvent


class LoanApplicationAggregate:
    def __init__(self, application_id: str) -> None:
        self.application_id = application_id
        self.state: ApplicationState | None = None
        self.version: int = -1
        self.applicant_id: str | None = None
        self.requested_amount_usd: Any = None
        self.credit_analysis_completed_count: int = 0
        self.human_review_superseded_credit: bool = False
        self.last_decision_recommendation: str | None = None
        self.session_ids_with_credit_decision: set[str] = set()

    @classmethod
    async def load(cls, store: Any, application_id: str) -> LoanApplicationAggregate:
        agg = cls(application_id=application_id)
        for ev in await store.load_stream(loan_stream_id(application_id)):
            agg._apply(ev)
        for ev in await store.load_stream(credit_stream_id(application_id)):
            agg._apply(ev)
        for ev in await store.load_stream(fraud_stream_id(application_id)):
            agg._apply(ev)
        for ev in await store.load_stream(compliance_stream_id(application_id)):
            agg._apply(ev)
        agg.version = await store.stream_version(loan_stream_id(application_id))
        return agg

    # ── Dispatch ────────────────────────────────────────────────────────────

    def _apply(self, event: StoredEvent) -> None:
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event)

    # ── Loan stream handlers ────────────────────────────────────────────────

    def _on_ApplicationSubmitted(self, event: StoredEvent) -> None:
        self.applicant_id = event.payload.get("applicant_id")
        self.requested_amount_usd = event.payload.get("requested_amount_usd")
        self.state = ApplicationState.SUBMITTED

    def _on_DocumentUploadRequested(self, event: StoredEvent) -> None:
        self.state = ApplicationState.DOCUMENTS_PENDING

    def _on_DocumentUploaded(self, event: StoredEvent) -> None:
        self.state = ApplicationState.DOCUMENTS_UPLOADED

    def _on_DocumentUploadFailed(self, event: StoredEvent) -> None:
        self.state = ApplicationState.DOCUMENTS_UPLOADED

    def _on_CreditAnalysisRequested(self, event: StoredEvent) -> None:
        self.state = ApplicationState.CREDIT_ANALYSIS_REQUESTED

    def _on_FraudScreeningRequested(self, event: StoredEvent) -> None:
        self.state = ApplicationState.FRAUD_SCREENING_REQUESTED

    def _on_ComplianceCheckRequested(self, event: StoredEvent) -> None:
        self.state = ApplicationState.COMPLIANCE_CHECK_REQUESTED

    def _on_DecisionRequested(self, event: StoredEvent) -> None:
        self.state = ApplicationState.PENDING_DECISION

    def _on_DecisionGenerated(self, event: StoredEvent) -> None:
        rec = (event.payload.get("recommendation") or "").upper()
        self.last_decision_recommendation = rec
        if rec == "REFER":
            self.state = ApplicationState.PENDING_HUMAN_REVIEW
        elif rec == "DECLINE":
            self.state = ApplicationState.DECLINED
        else:
            self.state = ApplicationState.PENDING_DECISION

    def _on_HumanReviewRequested(self, event: StoredEvent) -> None:
        self.state = ApplicationState.PENDING_HUMAN_REVIEW

    def _on_HumanReviewCompleted(self, event: StoredEvent) -> None:
        self.human_review_superseded_credit = bool(event.payload.get("override"))
        fd = (event.payload.get("final_decision") or "").upper()
        if "DECLINE" in fd or fd == "DECLINED":
            self.state = ApplicationState.DECLINED
        else:
            self.state = ApplicationState.PENDING_DECISION

    def _on_ApplicationApproved(self, event: StoredEvent) -> None:
        self.state = ApplicationState.APPROVED

    def _on_ApplicationDeclined(self, event: StoredEvent) -> None:
        self.state = ApplicationState.DECLINED

    # ── Cross-stream auxiliary handlers ──────────────────────────────────────

    def _on_CreditAnalysisCompleted(self, event: StoredEvent) -> None:
        self.credit_analysis_completed_count += 1
        sid = event.payload.get("session_id")
        if sid:
            self.session_ids_with_credit_decision.add(sid)
        if self.state == ApplicationState.CREDIT_ANALYSIS_REQUESTED:
            self.state = ApplicationState.CREDIT_ANALYSIS_COMPLETE

    def _on_FraudScreeningCompleted(self, event: StoredEvent) -> None:
        if self.state == ApplicationState.FRAUD_SCREENING_REQUESTED:
            self.state = ApplicationState.FRAUD_SCREENING_COMPLETE

    def _on_ComplianceCheckCompleted(self, event: StoredEvent) -> None:
        if self.state == ApplicationState.COMPLIANCE_CHECK_REQUESTED:
            self.state = ApplicationState.COMPLIANCE_CHECK_COMPLETE

    # ── Guards ───────────────────────────────────────────────────────────────

    def assert_not_already_submitted(self) -> None:
        if self.state is not None:
            raise DomainError(
                f"Application already submitted (state={self.state!r})"
            )

    def assert_pending_human_review(self) -> None:
        if self.state != ApplicationState.PENDING_HUMAN_REVIEW:
            raise DomainError(
                f"HumanReviewCompleted requires PENDING_HUMAN_REVIEW state, got {self.state!r}"
            )

    def assert_can_request_decision(self) -> None:
        allowed = {
            ApplicationState.COMPLIANCE_CHECK_REQUESTED,
            ApplicationState.COMPLIANCE_CHECK_COMPLETE,
        }
        if self.state not in allowed:
            raise DomainError(
                f"DecisionRequested requires compliance stage, got {self.state!r}"
            )

    def assert_can_approve(self) -> None:
        if self.state != ApplicationState.PENDING_DECISION:
            raise DomainError(
                f"ApplicationApproved requires PENDING_DECISION, got {self.state!r}"
            )

    def assert_can_append_second_credit_analysis(self) -> None:
        if self.credit_analysis_completed_count >= 1 and not self.human_review_superseded_credit:
            raise DomainError(
                "A second CreditAnalysisCompleted requires HumanReviewCompleted with override first"
            )

    def assert_contributing_sessions_valid(self, sessions: list[str]) -> None:
        for sid in sessions:
            if sid not in self.session_ids_with_credit_decision:
                raise DomainError(
                    f"Contributing session {sid!r} has no CreditAnalysisCompleted for this application"
                )

    def assert_decision_confidence_valid(self, confidence: float, recommendation: str) -> None:
        """Rule 4: confidence < 0.6 requires recommendation REFER."""
        if confidence < 0.6 and recommendation.upper() != "REFER":
            raise DomainError("confidence < 0.6 requires recommendation REFER")
