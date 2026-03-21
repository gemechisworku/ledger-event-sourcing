# Requirements layout → this repository

| Requirements reference | This repo |
|------------------------|-----------|
| `src/schema.sql` | `src/schema.sql` |
| `src/event_store.py` | `src/event_store.py` |
| `src/models/events.py` | `src/schema/events.py` |
| `src/aggregates/*` | `src/domain/aggregates/*` |
| `src/commands/handlers.py` | `src/domain/handlers.py` |
| `src/projections/*` | `src/projections/` (create) |
| `src/upcasting/*` | `src/upcasters.py` |
| `src/integrity/*` | `src/integrity/` (create) |
| `src/mcp/*` | `src/mcp_server.py` (+ split modules) |
| `src/what_if/*`, `src/regulatory/*` | Optional packages under `src/` |
| `datagen/*` | Existing — seed data pipeline |

Update `spec/00-index/traceability-matrix.md` when you add paths.
