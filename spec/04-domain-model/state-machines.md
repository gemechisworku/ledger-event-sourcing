# Loan application state machine

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## States (logical)

Map event types → states in code (`ApplicationState` enum). Reference chain:

1. **Submitted** — after `ApplicationSubmitted`
2. **AwaitingAnalysis** — after `CreditAnalysisRequested` or equivalent
3. **AnalysisComplete** — credit (and typically fraud) analyses recorded
4. **ComplianceReview** — compliance checks in flight / under review
5. **PendingDecision** — ready for orchestrator
6. **ApprovedPendingHuman** / **DeclinedPendingHuman** — after `DecisionGenerated` when human needed
7. **FinalApproved** / **FinalDeclined** — after `ApplicationApproved` / `ApplicationDeclined` (+ `HumanReviewCompleted` where applicable)

## Invalid examples

- Jump to **FinalApproved** without passing compliance + decision steps.
- **Approved** → **UnderReview** (explicitly forbidden by invariants table).

## Implementation

- `_apply(StoredEvent)` dispatches to `_on_<EventType>`.
- Each handler updates `self.state` and fields; validate **transition** before applying if using command handlers that emit multiple events.
