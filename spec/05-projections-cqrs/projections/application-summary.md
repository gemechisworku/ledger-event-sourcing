# Projection: ApplicationSummary

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Purpose

One row per **loan application** — current operational state for APIs and `ledger://applications/{id}`.

## Table columns (required)

| Column | Description |
|--------|-------------|
| application_id | PK |
| state | Derived enum from lifecycle |
| applicant_id | |
| requested_amount_usd | |
| approved_amount_usd | Nullable until approved |
| risk_tier | From credit analysis |
| fraud_score | From fraud screening |
| compliance_status | Aggregated from compliance projection/events |
| decision | Latest orchestrator / final |
| agent_sessions_completed | Array or JSON of session ids |
| last_event_type | |
| last_event_at | |
| human_reviewer_id | Nullable |
| final_decision_at | Nullable |

## Subscriptions

Subscribe to all event types that affect loan state: `ApplicationSubmitted`, `CreditAnalysisRequested`, `DecisionGenerated`, `HumanReviewCompleted`, `ApplicationApproved`, `ApplicationDeclined`, etc. — enumerate from [`../../04-domain-model/aggregates.md`](../../04-domain-model/aggregates.md).

## Updates

- **Upsert** on `application_id` — daemon applies event and updates row.
