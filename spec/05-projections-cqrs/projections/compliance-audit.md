# Projection: ComplianceAuditView

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Purpose

**Regulatory read model** — complete, traceable, time-queryable compliance state per application.

## Required API

| Method | Behaviour |
|--------|-----------|
| `get_current_compliance(application_id)` | All checks, verdicts, regulation versions |
| `get_compliance_at(application_id, timestamp)` | State as of **as_of** time |
| `get_projection_lag()` | Ms lag for this projection |
| `rebuild_from_scratch()` | Truncate + replay from `global_position` 0; **no downtime** for readers — use **blue/green table**, **version column**, or **read from old while rebuilding** (justify in `DESIGN.md`) |

## Snapshot strategy (must document in DESIGN.md)

Options: snapshot every N events, on timer, or on demand; invalidation rules when new compliance events arrive.

## Temporal query

- MCP: `ledger://applications/{id}/compliance?as_of=timestamp` — **p99 &lt; 200ms** target.

## Data completeness

- Every **ComplianceRulePassed** / **Failed**, **ComplianceCheckRequested** must be reflected.
- Every rule row references **regulation / rule version** for audit.
