# MCP resources (queries)

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

**Rule:** Resources read **projections** — **not** full aggregate replay on each request (except where noted).

| RESOURCE URI | DATA SOURCE | TEMPORAL? | SLO (p99) |
|--------------|---------------|-----------|-----------|
| `ledger://applications/{id}` | ApplicationSummary | No — current only | &lt; 50ms |
| `ledger://applications/{id}/compliance` | ComplianceAuditView | Yes — `?as_of=timestamp` | &lt; 200ms |
| `ledger://applications/{id}/audit-trail` | AuditLedger stream (**direct load** — justified) | Yes — `?from=&to=` | &lt; 500ms |
| `ledger://agents/{id}/performance` | AgentPerformanceLedger | No | &lt; 50ms |
| `ledger://agents/{id}/sessions/{session_id}` | AgentSession stream (**direct load**) | Yes — replay | &lt; 300ms |
| `ledger://ledger/health` | `ProjectionDaemon.get_all_lags()` | No | &lt; 10ms |

## Anti-pattern

Replaying all events on every read for ApplicationSummary — use projection table instead.
