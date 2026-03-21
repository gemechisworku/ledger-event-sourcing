# MCP architecture

- **FastMCP** — server entry in `ledger/mcp_server.py`.
- Structural **CQRS:** tools append via `EventStore`; resources read **projections** (avoid replaying streams on every query).
