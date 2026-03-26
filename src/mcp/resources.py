"""
MCP resources (query side) — projections and justified stream reads.

Justified stream replay (not served from projection tables):
  - ``ledger://applications/{id}/audit-trail`` — loan stream replay for audit visibility.
  - ``ledger://agents/{id}/sessions/{session_id}`` — agent session stream replay for session forensics.

All other resources read from projections or operational tables (e.g. agent performance SQL).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from src.domain.streams import agent_stream_id, audit_stream_id
from src.projections import (
    AgentPerformanceLedgerProjection,
    ApplicationSummaryProjection,
    ComplianceAuditProjection,
    ProjectionDaemon,
)


def register_resources(
    mcp: FastMCP,
    store: Any,
    daemon: ProjectionDaemon | None,
    app_sum: ApplicationSummaryProjection,
    comp: ComplianceAuditProjection,
    perf: AgentPerformanceLedgerProjection,
) -> None:
    """Register MCP resources (read paths)."""

    @mcp.resource("ledger://applications/{application_id}")
    async def resource_application(application_id: str) -> str:
        row = await app_sum._load_row(application_id)
        return json.dumps(row, default=str)

    @mcp.resource("ledger://applications/{application_id}/compliance")
    async def resource_compliance(application_id: str) -> str:
        cur = await comp.get_current_compliance(application_id)
        return json.dumps(cur, default=str)

    @mcp.resource("ledger://applications/{application_id}/compliance/at/{as_of_ts}")
    async def resource_compliance_at(application_id: str, as_of_ts: str) -> str:
        as_of = datetime.fromisoformat(as_of_ts.replace("Z", "+00:00"))
        result = await comp.get_compliance_at(application_id, as_of)
        return json.dumps(result, default=str)

    @mcp.resource("ledger://applications/{application_id}/audit-trail")
    async def resource_audit_trail(application_id: str) -> str:
        sid = audit_stream_id("loan", application_id)
        evs = await store.load_stream(sid)
        return json.dumps(
            [{"event_type": e.event_type, "stream_position": e.stream_position, "payload": e.payload} for e in evs],
            default=str,
        )

    @mcp.resource("ledger://agents/{agent_id}/performance")
    async def resource_agent_performance(agent_id: str) -> str:
        pool = getattr(store, "pool", None) or getattr(store, "_pool", None)
        if pool is None:
            rows = [v for (a, m), v in perf._mem.items() if a == agent_id]
            return json.dumps(rows, default=str)
        async with pool.acquire() as conn:
            recs = await conn.fetch(
                "SELECT * FROM projection_agent_performance WHERE agent_id = $1",
                agent_id,
            )
            return json.dumps([dict(r) for r in recs], default=str)

    @mcp.resource("ledger://agents/{agent_id}/sessions/{session_id}")
    async def resource_agent_session(agent_id: str, session_id: str) -> str:
        sid = agent_stream_id(agent_id, session_id)
        evs = await store.load_stream(sid)
        return json.dumps(
            [{"event_type": e.event_type, "stream_position": e.stream_position, "payload": e.payload} for e in evs],
            default=str,
        )

    @mcp.resource("ledger://ledger/health")
    async def resource_health() -> str:
        if daemon is None:
            return json.dumps({"lags": {}, "lags_ms": {}, "note": "daemon not attached"})
        lags = await daemon.get_all_lags()
        lags_ms = await daemon.get_all_lags_ms()
        return json.dumps({"lags": lags, "lags_ms": lags_ms})
