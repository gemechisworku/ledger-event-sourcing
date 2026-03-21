# MCP tools (commands)

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 5.

| TOOL NAME | COMMAND / EVENT | CRITICAL VALIDATION | RETURN (typical) |
|-----------|-----------------|---------------------|------------------|
| `submit_application` | `ApplicationSubmitted` | Pydantic schema; **no duplicate** `application_id` | `stream_id`, `initial_version` |
| `record_credit_analysis` | `CreditAnalysisCompleted` | Active `AgentSession` with **context loaded**; OCC on loan stream | `event_id`, `new_stream_version` |
| `record_fraud_screening` | `FraudScreeningCompleted` | Same session rules; **`fraud_score` ∈ [0.0, 1.0]** | `event_id`, `new_stream_version` |
| `record_compliance_check` | `ComplianceRulePassed` / `Failed` | `rule_id` ∈ active **regulation_set_version** | `check_id`, `compliance_status` |
| `generate_decision` | `DecisionGenerated` | Required analyses present; **confidence floor** (→ REFER if &lt; 0.6) | `decision_id`, `recommendation` |
| `record_human_review` | `HumanReviewCompleted` | `reviewer_id` auth; if `override=True` → **`override_reason` required** | `final_decision`, `application_state` |
| `start_agent_session` | `AgentContextLoaded` | **Must** run before other agent tools; sets context source + token count | `session_id`, `context_position` |
| `run_integrity_check` | `AuditIntegrityCheckRun` | Compliance role only; **rate limit** e.g. 1/min/entity | `check_result`, `chain_valid` |

## Implementation

- Map to FastMCP tool decorators; wire to command handlers + `EventStore`.
