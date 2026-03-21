"""
LoanApplication aggregate — stream `loan-{application_id}`.
Replays loan, credit, fraud, and compliance streams for a coherent application state.
"""

from __future__ import annotations

from typing import Any

from src.domain.errors import DomainError
from src.domain.streams import compliance_stream_id, credit_stream_id, fraud_stream_id, loan_stream_id
from src.schema.events import ApplicationState


_LOAN_ONLY: dict[str, ApplicationState] = {
    "ApplicationSubmitted": ApplicationState.SUBMITTED,
    "DocumentUploadRequested": ApplicationState.DOCUMENTS_PENDING,
    "DocumentUploaded": ApplicationState.DOCUMENTS_UPLOADED,
    "DocumentUploadFailed": ApplicationState.DOCUMENTS_UPLOADED,
    "CreditAnalysisRequested": ApplicationState.CREDIT_ANALYSIS_REQUESTED,
    "FraudScreeningRequested": ApplicationState.FRAUD_SCREENING_REQUESTED,
    "ComplianceCheckRequested": ApplicationState.COMPLIANCE_CHECK_REQUESTED,
    "DecisionRequested": ApplicationState.PENDING_DECISION,
    "HumanReviewRequested": ApplicationState.PENDING_HUMAN_REVIEW,
    "ApplicationApproved": ApplicationState.APPROVED,
    "ApplicationDeclined": ApplicationState.DECLINED,
}

_ALLOWED_PRIOR: dict[str, frozenset[ApplicationState | None]] = {
    "ApplicationSubmitted": frozenset({None}),
    "DocumentUploadRequested": frozenset({ApplicationState.SUBMITTED}),
    "DocumentUploaded": frozenset({ApplicationState.DOCUMENTS_PENDING}),
    "DocumentUploadFailed": frozenset({ApplicationState.DOCUMENTS_PENDING}),
    "CreditAnalysisRequested": frozenset(
        {ApplicationState.DOCUMENTS_UPLOADED, ApplicationState.SUBMITTED}
    ),
    "FraudScreeningRequested": frozenset(
        {ApplicationState.CREDIT_ANALYSIS_REQUESTED, ApplicationState.CREDIT_ANALYSIS_COMPLETE}
    ),
    "ComplianceCheckRequested": frozenset(
        {ApplicationState.FRAUD_SCREENING_REQUESTED, ApplicationState.FRAUD_SCREENING_COMPLETE}
    ),
    "DecisionRequested": frozenset(
        {ApplicationState.COMPLIANCE_CHECK_REQUESTED, ApplicationState.COMPLIANCE_CHECK_COMPLETE}
    ),
    "DecisionGenerated": frozenset({ApplicationState.PENDING_DECISION}),
    "HumanReviewRequested": frozenset({ApplicationState.PENDING_HUMAN_REVIEW}),
    "HumanReviewCompleted": frozenset({ApplicationState.PENDING_HUMAN_REVIEW}),
    "ApplicationApproved": frozenset({ApplicationState.PENDING_DECISION}),
    "ApplicationDeclined": frozenset(
        {ApplicationState.PENDING_DECISION, ApplicationState.PENDING_HUMAN_REVIEW}
    ),
}


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
            agg._apply_loan(ev)
        for ev in await store.load_stream(credit_stream_id(application_id)):
            agg._apply_credit_aux(ev)
        for ev in await store.load_stream(fraud_stream_id(application_id)):
            agg._apply_fraud_aux(ev)
        for ev in await store.load_stream(compliance_stream_id(application_id)):
            agg._apply_compliance_aux(ev)
        agg.version = await store.stream_version(loan_stream_id(application_id))
        return agg

    def _apply_loan(self, event: dict) -> None:
        et = event["event_type"]
        p = event.get("payload", {})

        allowed = _ALLOWED_PRIOR.get(et)
        if allowed is not None and self.state not in allowed:
            raise DomainError(
                f"Invalid loan transition: cannot apply {et} from state {self.state!r}"
            )

        if et == "ApplicationSubmitted":
            self.applicant_id = p.get("applicant_id")
            self.requested_amount_usd = p.get("requested_amount_usd")
            self.state = ApplicationState.SUBMITTED
        elif et == "DecisionGenerated":
            rec = (p.get("recommendation") or "").upper()
            self.last_decision_recommendation = rec
            if rec == "REFER":
                self.state = ApplicationState.PENDING_HUMAN_REVIEW
            elif rec == "DECLINE":
                self.state = ApplicationState.DECLINED
            else:
                self.state = ApplicationState.PENDING_DECISION
        elif et == "HumanReviewCompleted":
            self.human_review_superseded_credit = bool(p.get("override"))
            fd = (p.get("final_decision") or "").upper()
            if "DECLINE" in fd or fd == "DECLINED":
                self.state = ApplicationState.DECLINED
            else:
                self.state = ApplicationState.PENDING_DECISION
        elif et in _LOAN_ONLY:
            self.state = _LOAN_ONLY[et]

    def _apply_credit_aux(self, event: dict) -> None:
        et = event["event_type"]
        p = event.get("payload", {})
        if et == "CreditAnalysisCompleted":
            self.credit_analysis_completed_count += 1
            sid = p.get("session_id")
            if sid:
                self.session_ids_with_credit_decision.add(sid)
            if self.state == ApplicationState.CREDIT_ANALYSIS_REQUESTED:
                self.state = ApplicationState.CREDIT_ANALYSIS_COMPLETE
        elif et == "CreditRecordOpened":
            pass

    def _apply_fraud_aux(self, event: dict) -> None:
        et = event["event_type"]
        if et == "FraudScreeningCompleted":
            if self.state == ApplicationState.FRAUD_SCREENING_REQUESTED:
                self.state = ApplicationState.FRAUD_SCREENING_COMPLETE
        elif et == "FraudScreeningInitiated":
            pass

    def _apply_compliance_aux(self, event: dict) -> None:
        et = event["event_type"]
        if et == "ComplianceCheckCompleted":
            if self.state == ApplicationState.COMPLIANCE_CHECK_REQUESTED:
                self.state = ApplicationState.COMPLIANCE_CHECK_COMPLETE
        elif et == "ComplianceCheckInitiated":
            pass

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
