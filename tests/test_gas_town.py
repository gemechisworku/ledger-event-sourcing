"""Gas Town — agent context reconstruction."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.domain.streams import agent_stream_id
from src.event_store import InMemoryEventStore
from src.gas_town import reconstruct_agent_context
from src.schema.events import AgentType


def _sess(agent_type: str, session_id: str, seq: int) -> dict:
    return {
        "event_type": "AgentNodeExecuted",
        "event_version": 1,
        "payload": {
            "session_id": session_id,
            "agent_type": agent_type,
            "node_name": f"n{seq}",
            "node_sequence": seq,
            "input_keys": [],
            "output_keys": [],
            "llm_called": False,
            "duration_ms": 1,
            "executed_at": "2026-01-01T00:00:00+00:00",
        },
    }


@pytest.mark.asyncio
async def test_reconstruct_after_five_events():
    store = InMemoryEventStore()
    at = AgentType.CREDIT_ANALYSIS.value
    sid = "sess-gas-01"
    stream = agent_stream_id(at, sid)
    for i in range(5):
        ver = await store.stream_version(stream)
        await store.append(stream, [_sess(at, sid, i)], expected_version=ver)

    ctx = await reconstruct_agent_context(store, at, sid)
    assert ctx.last_event_position >= 0
    assert len(ctx.verbatim_tail) <= 3
    assert ctx.session_health_status == "IN_PROGRESS"
