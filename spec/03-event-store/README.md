# Event store core (Phase 1)

| Doc | Purpose |
|-----|---------|
| `requirements.md` | `EventStore` interface: `append`, `load_stream`, `load_all`, metadata, archive |
| `schema-contract.md` | Tables, indexes, constraints — column rationale → `DESIGN.md` |
| `concurrency-and-outbox.md` | OCC semantics, transaction boundaries, outbox |
| `double-decision-test.md` | Concurrent append test spec |

**Code:** `ledger/event_store.py` (+ SQL migrations if you add `schema.sql`).
