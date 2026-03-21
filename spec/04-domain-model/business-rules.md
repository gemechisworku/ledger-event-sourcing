# Business rules

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 2.

All rules must live in **aggregate / domain** code, not only API or MCP handlers.

## 1. Application state machine

Valid transitions only:

`Submitted` → `AwaitingAnalysis` → `AnalysisComplete` → `ComplianceReview` → `PendingDecision` → `ApprovedPendingHuman` / `DeclinedPendingHuman` → `FinalApproved` / `FinalDeclined`

- Any **out-of-order** transition → **`DomainError`**.

## 2. Gas Town — AgentSession

- **`AgentContextLoaded`** must be the **first** event (or first before any “decision” class event) on the AgentSession stream.
- No decision-class event without prior context declaration.

## 3. Model version locking (credit analysis churn)

- After **`CreditAnalysisCompleted`** for an application, **no second** `CreditAnalysisCompleted` for the same application unless the first was superseded by **`HumanReviewOverride`** (or equivalent event you define).

## 4. Confidence floor (DecisionGenerated)

- If `confidence_score < 0.6` → **`recommendation` must be `"REFER"`**, regardless of orchestrator output.

## 5. Compliance dependency (ApplicationApproved)

- **`ApplicationApproved`** cannot append unless all **`ComplianceRulePassed`** events for **required** checks exist on **`compliance-{application_id}`** stream.
- LoanApplication aggregate may need to **read** compliance stream state or hold denormalized references updated via process manager / saga (document choice in `DESIGN.md`).

## 6. Causal chain (DecisionGenerated)

- `contributing_agent_sessions[]` must list only session streams that **actually** contain a decision event for this `application_id`.
- Reject orchestrator output that references unrelated sessions.
