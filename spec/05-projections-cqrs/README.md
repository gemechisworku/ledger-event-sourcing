# Projections & CQRS (Phase 4)

| Doc | Purpose |
|-----|---------|
| `daemon.md` | `ProjectionDaemon`: polling, checkpoints, retries, `get_lag()`, fault tolerance |
| `slo-and-lag.md` | SLO numbers, load-test assumptions |
| `projections/application-summary.md` | Table columns, event subscriptions |
| `projections/agent-performance.md` | Metrics dimensions |
| `projections/compliance-audit.md` | Temporal API, snapshot strategy, `rebuild_from_scratch` |

**Code:** `ledger/projections/` (create); checkpoints table in schema spec.
