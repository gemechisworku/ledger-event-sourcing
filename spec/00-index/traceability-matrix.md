# Traceability matrix (living document)

| Phase | Focus | Primary code in this repo | Tests |
|-------|--------|---------------------------|--------|
| 0 | Schema + generator | `ledger/schema/events.py`, `datagen/*` | `tests/test_schema_and_generator.py` |
| 1 | Event store + registry | `ledger/event_store.py`, `ledger/registry/client.py` | `tests/test_event_store.py` |
| 2 | Aggregates + agents | `ledger/domain/aggregates/`, `ledger/agents/base_agent.py` | `tests/test_domain.py` |
| 3 | Narratives / multi-agent | `ledger/agents/*` | `tests/test_narratives.py` |
| 4 | Projections + daemon + upcasters | `ledger/projections/`, `ledger/upcasters.py` | `tests/test_projections.py` |
| 5 | MCP server | `ledger/mcp_server.py` | `tests/test_mcp.py` |
| 6 (optional) | What-if + regulatory package | e.g. `ledger/what_if/`, `ledger/regulatory/` | Additional suites as added |

**Note:** External references may use `src/…` or extra test names (`test_concurrency.py`, `test_mcp_lifecycle.py`). Map new files here when introduced.
