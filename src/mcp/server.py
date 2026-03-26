"""
MCP server entry — tools append to EventStore; resources read projections / streams.

Requires `start_agent_session` before `record_credit_analysis`, `record_fraud_screening`, etc.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from src.mcp.resources import register_resources
from src.mcp.tools import register_tools
from src.projections import (
    AgentPerformanceLedgerProjection,
    ApplicationSummaryProjection,
    ComplianceAuditProjection,
    ProjectionDaemon,
)
from src.upcasting.upcasters import default_upcaster_registry


def build_mcp_server(
    store: Any,
    *,
    daemon: ProjectionDaemon | None = None,
    application_summary: ApplicationSummaryProjection | None = None,
    compliance_audit: ComplianceAuditProjection | None = None,
    agent_performance: AgentPerformanceLedgerProjection | None = None,
) -> FastMCP:
    """
    Build FastMCP app. Pass PostgreSQL-backed EventStore for production; InMemoryEventStore for tests.
    """
    app_sum = application_summary or ApplicationSummaryProjection(store)
    comp = compliance_audit or ComplianceAuditProjection(store)
    perf = agent_performance or AgentPerformanceLedgerProjection(store)

    mcp = FastMCP(
        "ledger",
        instructions=(
            "The Ledger MCP: tools mutate append-only streams; resources read projections. "
            "Call start_agent_session before record_credit_analysis / record_fraud_screening / "
            "record_compliance_check. On OptimisticConcurrencyError, reload streams and retry."
        ),
    )
    register_tools(mcp, store)
    register_resources(mcp, store, daemon, app_sum, comp, perf)
    return mcp


async def run_stdio_server() -> None:
    import os

    try:
        from dotenv import load_dotenv

        _root = Path(__file__).resolve().parent.parent.parent
        load_dotenv(_root / ".env")
    except ImportError:
        pass

    from src.event_store import EventStore

    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DB_URL")
    if not url:
        raise RuntimeError("DATABASE_URL or TEST_DB_URL required")
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
    await mcp.run_stdio_async()


def main() -> None:
    import asyncio

    asyncio.run(run_stdio_server())


if __name__ == "__main__":
    main()
