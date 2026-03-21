# Projection: AgentPerformanceLedger

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Purpose

Per **`agent_id`** + **`model_version`** aggregates — compare behaviour across model releases.

## Table columns

| Column | Description |
|--------|-------------|
| agent_id | |
| model_version | |
| analyses_completed | Counter |
| decisions_generated | Counter |
| avg_confidence_score | |
| avg_duration_ms | |
| approve_rate | |
| decline_rate | |
| refer_rate | |
| human_override_rate | |
| first_seen_at | |
| last_seen_at | |

## Event sources

- `CreditAnalysisCompleted`, `DecisionGenerated`, `HumanReviewCompleted`, etc. — any event carrying agent identity + model version.

## Queries

- Powers `ledger://agents/{id}/performance`.
