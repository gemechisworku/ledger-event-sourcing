"""Gas Town — agent context reconstruction."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.domain.streams import agent_stream_id
from src.event_store import InMemoryEventStore
from src.integrity.gas_town import reconstruct_agent_context
from src.models.events import AgentNodeExecuted, AgentSessionFailed, AgentSessionStarted, AgentType


@pytest.mark.asyncio
async def test_reconstruct_after_five_events_with_started_and_failure():
    store = InMemoryEventStore()
    at = AgentType.CREDIT_ANALYSIS
    sid = "sess-gas-01"
    stream = agent_stream_id(at.value, sid)
    dt = datetime.now(timezone.utc)

    seq = [
        AgentSessionStarted(
            session_id=sid,
            agent_type=at,
            agent_id="ag1",
            application_id="APP-1",
            model_version="mv1",
            langgraph_graph_version="1",
            context_source="replay",
            context_token_count=0,
            started_at=dt,
        ).to_store_dict(),
        AgentNodeExecuted(
            session_id=sid,
            agent_type=at,
            node_name="n0",
            node_sequence=0,
            input_keys=[],
            output_keys=[],
            llm_called=False,
            duration_ms=1,
            executed_at=dt,
        ).to_store_dict(),
        AgentNodeExecuted(
            session_id=sid,
            agent_type=at,
            node_name="n1",
            node_sequence=1,
            input_keys=[],
            output_keys=[],
            llm_called=False,
            duration_ms=1,
            executed_at=dt,
        ).to_store_dict(),
        AgentNodeExecuted(
            session_id=sid,
            agent_type=at,
            node_name="n2",
            node_sequence=2,
            input_keys=[],
            output_keys=[],
            llm_called=False,
            duration_ms=1,
            executed_at=dt,
        ).to_store_dict(),
        AgentSessionFailed(
            session_id=sid,
            agent_type=at,
            application_id="APP-1",
            error_type="timeout",
            error_message="upstream",
            recoverable=True,
            failed_at=dt,
        ).to_store_dict(),
    ]

    for ev in seq:
        v = await store.stream_version(stream)
        await store.append(stream, [ev], expected_version=v)

    ctx = await reconstruct_agent_context(store, at.value, sid)
    assert ctx.last_event_position == 4
    assert ctx.pending_work
    assert ctx.session_health_status == "NEEDS_RECONCILIATION"
    assert len(ctx.verbatim_tail) <= 3


@pytest.mark.asyncio
async def test_decision_node_without_completion_flags_reconciliation():
    store = InMemoryEventStore()
    at = AgentType.CREDIT_ANALYSIS
    sid = "sess-dec"
    stream = agent_stream_id(at.value, sid)
    dt = datetime.now(timezone.utc)
    evs = [
        AgentSessionStarted(
            session_id=sid,
            agent_type=at,
            agent_id="ag1",
            application_id="APP-2",
            model_version="mv1",
            langgraph_graph_version="1",
            context_source="replay",
            context_token_count=0,
            started_at=dt,
        ).to_store_dict(),
        AgentNodeExecuted(
            session_id=sid,
            agent_type=at,
            node_name="credit_decision_final",
            node_sequence=0,
            input_keys=[],
            output_keys=[],
            llm_called=False,
            duration_ms=1,
            executed_at=dt,
        ).to_store_dict(),
    ]
    for ev in evs:
        v = await store.stream_version(stream)
        await store.append(stream, [ev], expected_version=v)
    ctx = await reconstruct_agent_context(store, at.value, sid)
    assert ctx.session_health_status == "NEEDS_RECONCILIATION"
