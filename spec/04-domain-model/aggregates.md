# Aggregates

## Reference (summary)

| Aggregate | Stream | Tracks |
|-----------|--------|--------|
| LoanApplication | `loan-{application_id}` | Lifecycle |
| AgentSession | `agent-{agent_id}-{session_id}` | Session actions, Gas Town |
| ComplianceRecord | `compliance-{application_id}` | Rules / regulation versions |
| AuditLedger | `audit-{entity_type}-{entity_id}` | Cross-cutting audit + correlation |

## Starter repo

- `ledger/domain/aggregates/loan_application.py` — extend per state machine + rules.
- Add **ComplianceRecord** and **AuditLedger** when implemented.
