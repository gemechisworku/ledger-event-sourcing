#!/usr/bin/env python3
"""
Run the Ledger MCP over Streamable HTTP so multiple clients (two terminals) can call tools concurrently.

  uv run python scripts/run_mcp_http.py

Env:
  DATABASE_URL or TEST_DB_URL — required
  MCP_HTTP_HOST — default 127.0.0.1 (use 0.0.0.0 in Docker to expose)
  MCP_HTTP_PORT — default 8765

Default URL: http://127.0.0.1:8765/mcp
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass


async def main() -> None:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DB_URL")
    if not url:
        print("Set DATABASE_URL or TEST_DB_URL", file=sys.stderr)
        sys.exit(1)

    host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_HTTP_PORT", "8765"))

    from src.event_store import EventStore
    from src.mcp_server import build_mcp_server
    from src.projections import (
        AgentPerformanceLedgerProjection,
        ApplicationSummaryProjection,
        ComplianceAuditProjection,
        ProjectionDaemon,
    )
    from src.upcasters import default_upcaster_registry

    store = EventStore(url, upcaster_registry=default_upcaster_registry())
    await store.connect()
    projs = [
        ApplicationSummaryProjection(store),
        AgentPerformanceLedgerProjection(store),
        ComplianceAuditProjection(store),
    ]
    daemon = ProjectionDaemon(store, projs)
    mcp = build_mcp_server(
        store,
        daemon=daemon,
        application_summary=projs[0],
        agent_performance=projs[1],
        compliance_audit=projs[2],
    )
    await mcp.run_http_async(host=host, port=port, transport="streamable-http")


if __name__ == "__main__":
    asyncio.run(main())
