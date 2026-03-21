# Projections & CQRS

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 3 (document uses “Phase 3” for projections; README roadmap uses Phase 4).

| Doc | Purpose |
|-----|---------|
| [`daemon.md`](daemon.md) | `ProjectionDaemon`, batching, checkpoints, fault tolerance, lag |
| [`slo-and-lag.md`](slo-and-lag.md) | 500ms / 2s SLOs, load test |
| [`projections/application-summary.md`](projections/application-summary.md) | ApplicationSummary columns |
| [`projections/agent-performance.md`](projections/agent-performance.md) | AgentPerformanceLedger columns |
| [`projections/compliance-audit.md`](projections/compliance-audit.md) | ComplianceAuditView + temporal + rebuild |

**Code:** `ledger/projections/` (to create).
