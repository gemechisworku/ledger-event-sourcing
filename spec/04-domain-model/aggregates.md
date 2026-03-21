# Aggregates

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Four aggregates — streams and invariants

| AGGREGATE | STREAM ID FORMAT | TRACKS | KEY INVARIANTS |
|-----------|------------------|--------|----------------|
| LoanApplication | `loan-{application_id}` | Full lifecycle from submission to decision | Cannot transition from Approved → UnderReview; cannot approve if compliance pending; credit limit ≤ agent-assessed max |
| AgentSession | `agent-{agent_id}-{session_id}` | Actions in one agent session (model version, hashes, traces, outputs) | Every output references **ContextLoaded**; every decision references **model version** used |
| ComplianceRecord | `compliance-{application_id}` | Regulatory checks and verdicts | No clearance without **all** mandatory checks; each check references **regulation version** |
| AuditLedger | `audit-{entity_type}-{entity_id}` | Cross-entity audit trail | Append-only; **correlation_id** chains preserve causal ordering |

## Event catalogue (starter — may be incomplete)

| EVENT TYPE | AGGREGATE | VER | KEY PAYLOAD FIELDS |
|------------|-----------|-----|---------------------|
| ApplicationSubmitted | LoanApplication | 1 | application_id, applicant_id, requested_amount_usd, loan_purpose, submission_channel, submitted_at |
| CreditAnalysisRequested | LoanApplication | 1 | application_id, assigned_agent_id, requested_at, priority |
| CreditAnalysisCompleted | AgentSession | 2 | application_id, agent_id, session_id, model_version, confidence_score, risk_tier, recommended_limit_usd, analysis_duration_ms, input_data_hash |
| FraudScreeningCompleted | AgentSession | 1 | application_id, agent_id, fraud_score, anomaly_flags[], screening_model_version, input_data_hash |
| ComplianceCheckRequested | ComplianceRecord | 1 | application_id, regulation_set_version, checks_required[] |
| ComplianceRulePassed | ComplianceRecord | 1 | application_id, rule_id, rule_version, evaluation_timestamp, evidence_hash |
| ComplianceRuleFailed | ComplianceRecord | 1 | application_id, rule_id, rule_version, failure_reason, remediation_required |
| DecisionGenerated | LoanApplication | 2 | application_id, orchestrator_agent_id, recommendation (APPROVE/DECLINE/REFER), confidence_score, contributing_agent_sessions[], decision_basis_summary, model_versions{} |
| HumanReviewCompleted | LoanApplication | 1 | application_id, reviewer_id, override, final_decision, override_reason (if override) |
| ApplicationApproved | LoanApplication | 1 | application_id, approved_amount_usd, interest_rate, conditions[], approved_by, effective_date |
| ApplicationDeclined | LoanApplication | 1 | application_id, decline_reasons[], declined_by, adverse_action_notice_required |
| AgentContextLoaded | AgentSession | 1 | agent_id, session_id, context_source, event_replay_from_position, context_token_count, model_version |
| AuditIntegrityCheckRun | AuditLedger | 1 | entity_id, check_timestamp, events_verified_count, integrity_hash, previous_hash |

**Gap analysis:** Requirements state the catalogue is **incomplete** — identify missing events (e.g. transitions, intermediate states) and add to `src/schema/events.py` + registry.

## Code layout

- `src/domain/aggregates/loan_application.py` — extend
- Add `compliance_record.py`, `audit_ledger.py` as needed
- `AgentSession` — same folder or `agent_session.py`
