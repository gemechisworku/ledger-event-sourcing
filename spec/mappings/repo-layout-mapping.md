# External layout → this repository

| Typical `src/` path | This repo |
|---------------------|-----------|
| `src/schema.sql` | e.g. `ledger/schema.sql` or `schema/` migrations |
| `src/event_store.py` | `ledger/event_store.py` |
| `src/models/events.py` | `ledger/schema/events.py` (+ wrappers if split) |
| `src/aggregates/*` | `ledger/domain/aggregates/*` |
| `src/commands/handlers.py` | e.g. `ledger/commands/` or next to aggregates |
| `src/projections/*` | `ledger/projections/` (create) |
| `src/upcasting/*` | `ledger/upcasters.py` or `ledger/upcasting/` |
| `src/integrity/*` | e.g. `ledger/integrity/` |
| `src/mcp/*` | `ledger/mcp_server.py` (+ split modules) |
| `src/what_if/*`, `src/regulatory/*` | Optional packages under `ledger/` |
| `datagen/*` | Existing — seed data pipeline |

Update `spec/00-index/traceability-matrix.md` when you add paths.
