# MCP layer (Phase 5)

| Doc | Purpose |
|-----|---------|
| `architecture.md` | CQRS mapping: tools = commands, resources = queries |
| `tools-spec.md` | Eight tools: names, validations, return shapes |
| `resources-spec.md` | Six resource URIs, projection sources, SLO targets |
| `errors-for-llms.md` | Structured error schema + `suggested_action` + preconditions in descriptions |

**Code:** `ledger/mcp_server.py` (and optional `ledger/mcp/tools.py`, `resources.py`).
