# Loan application state machine

Valid flow:

`Submitted` → `AwaitingAnalysis` → `AnalysisComplete` → `ComplianceReview` → `PendingDecision` → `ApprovedPendingHuman` / `DeclinedPendingHuman` → `FinalApproved` / `FinalDeclined`

Document illegal transitions and `DomainError` behaviour.
