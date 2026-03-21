# Vision & scenario

**Canonical source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Product vision

The Ledger is **append-only, shared memory** for multi-agent systems: not fire-and-forget messaging, but **events as source of truth** so decisions are auditable, replayable, and queryable in time.

## Apex Financial Services — scenario

- **Agents:** CreditAnalysis, FraudDetection, Compliance, DecisionOrchestrator — plus **human loan officers** for binding decisions.
- **Regulatory bar:** Immutable audit trail; reconstruct state at any point; temporal / what-if style questions; **tamper detection** on the audit trail.
- **Architecture principle:** Auditability is **built in**, not bolted on after the fact.

## Operational demo standard

End-to-end: *“Complete decision history for application X”* — all agent actions, compliance, human review, causal links, temporal query at any lifecycle point, cryptographic integrity — **under ~60 seconds** for ops/demo use.

## Four aggregates (summary)

| Aggregate | Stream pattern | Role |
|-----------|----------------|------|
| LoanApplication | `loan-{application_id}` | Application lifecycle |
| AgentSession | `agent-{agent_id}-{session_id}` | Session-scoped agent actions, Gas Town |
| ComplianceRecord | `compliance-{application_id}` | Rules, regulation versions, verdicts |
| AuditLedger | `audit-{entity_type}-{entity_id}` | Cross-cutting audit, correlation chains |

Full invariant table: [`../04-domain-model/aggregates.md`](../04-domain-model/aggregates.md).
