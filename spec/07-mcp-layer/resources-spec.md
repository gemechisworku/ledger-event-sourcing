# MCP resources (query side)

| URI pattern | Source | Temporal? |
|-------------|--------|-----------|
| `ledger://applications/{id}` | ApplicationSummary | No |
| `ledger://applications/{id}/compliance` | ComplianceAuditView | Yes (`as_of`) |
| `ledger://applications/{id}/audit-trail` | Audit stream (exception) | Range |
| `ledger://agents/{id}/performance` | AgentPerformanceLedger | No |
| `ledger://agents/{id}/sessions/{session_id}` | AgentSession stream | Replay |
| `ledger://ledger/health` | Daemon lags | No |

**Rule:** resources do not replay full aggregates for every read; exceptions documented.
