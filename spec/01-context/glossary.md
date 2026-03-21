# Glossary

Aligned with [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — *Phase 0 — Domain reconnaissance*.

| Term | Definition |
|------|------------|
| **EDA** | Events as **messages** between components; sender may fire-and-forget; delivery not the DB truth. |
| **Event sourcing (ES)** | Events **are** the database; state = replay of history. |
| **Aggregate** | Consistency boundary; mutations emit domain events; aggregates interact via events, not direct calls across boundaries. |
| **CQRS** | Commands append events; queries read **projections**. MCP: **Tools ≈ commands**, **Resources ≈ queries**. |
| **OCC** | `expected_version` on append; conflict → exception → caller reloads and retries. |
| **Inline projection** | Updated in same transaction as write — stronger consistency, higher write latency. |
| **Async projection** | Background daemon — eventual consistency, rebuild by replay. |
| **Upcasting** | Transform old payload shape **at read time**; stored bytes never rewritten. |
| **Outbox** | Same DB transaction as event append; separate publisher drains for Kafka/bus. |
| **Gas Town** | Persist agent context/actions in the store before acting; replay stream after restart to restore context. |

## Stack reference (orientation)

| Tool | Role for this project |
|------|------------------------|
| PostgreSQL + async driver | **Primary** event store |
| EventStoreDB | Reference API / mapping in `DESIGN.md` |
| Marten / Wolverine | Conceptual parallel (async daemon, routing) |
| Kafka | Outbox → integration |
| Redis Streams | Optional low-latency fan-out |
