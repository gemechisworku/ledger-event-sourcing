# Streams & events

## Stream naming

| Prefix | Aggregate |
|--------|-----------|
| `loan-` | LoanApplication |
| `agent-` | AgentSession — format `agent-{agent_id}-{session_id}` |
| `compliance-` | ComplianceRecord — `compliance-{application_id}` |
| `audit-` | AuditLedger — `audit-{entity_type}-{entity_id}` |

## Catalogue vs code

- **Authoritative models:** `src/schema/events.py`, `EVENT_REGISTRY`, datagen validator.
- **Drift:** Compare [`aggregates.md`](aggregates.md) table to `EVENT_REGISTRY`; add missing types and versions.

## Metadata

- Use `metadata` on stored events for **correlation_id**, **causation_id**, **actor**, **schema_version** — required for MCP integration tests and audit trail.

## Multi-stream workflows

- One user action may require **multiple appends** (e.g. loan stream + agent stream). Define **order** and **idempotency**; use same `correlation_id` across streams.
