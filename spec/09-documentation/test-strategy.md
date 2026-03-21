# Test strategy

| Concern | Tests |
|---------|--------|
| Schema + generator | `tests/test_schema_and_generator.py` |
| Event store + OCC | `tests/test_event_store.py` (+ concurrency suite when split) |
| Domain | `tests/test_domain.py` |
| Agents / narratives | `tests/test_narratives.py` |
| Projections + lag | `tests/test_projections.py` |
| MCP | `tests/test_mcp.py` |
| Optional extras | `test_upcasting`, `test_gas_town`, `test_mcp_lifecycle` — add when present |

Link each to specs in `03`–`07`.
