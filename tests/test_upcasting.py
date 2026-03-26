"""Upcasting on load — immutable DB rows, v2-shaped consumer view."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.event_store import InMemoryEventStore
from src.upcasters import default_upcaster_registry


@pytest.mark.asyncio
async def test_credit_v1_load_adds_regulatory_basis():
    store = InMemoryEventStore()
    store.upcasters = default_upcaster_registry()
    ev = {
        "event_type": "CreditAnalysisCompleted",
        "event_version": 1,
        "payload": {
            "application_id": "A",
            "session_id": "S",
            "decision": {"risk_tier": "LOW", "recommended_limit_usd": "1", "confidence": 0.9},
        },
    }
    await store.append("credit-A", [ev], expected_version=-1)
    loaded = await store.load_stream("credit-A")
    assert len(loaded) == 1
    assert loaded[0].event_version >= 2
    assert "regulatory_basis" in loaded[0].payload


@pytest.mark.asyncio
async def test_v1_row_immutable_upcast_only_on_load():
    """Raw stored row stays v1-shaped; load_stream returns v2-shaped view."""
    store = InMemoryEventStore()
    store.upcasters = default_upcaster_registry()
    ev = {
        "event_type": "CreditAnalysisCompleted",
        "event_version": 1,
        "payload": {
            "application_id": "A",
            "session_id": "S",
            "decision": {"risk_tier": "LOW", "recommended_limit_usd": "1", "confidence": 0.9},
        },
    }
    await store.append("credit-B", [ev], expected_version=-1)
    raw = await store.get_event_raw((await store.load_stream_persisted("credit-B"))[0].event_id)
    assert raw is not None
    assert raw.event_version == 1
    assert "regulatory_basis" not in raw.payload
    up = await store.load_stream("credit-B")
    assert up[0].event_version >= 2
    assert "regulatory_basis" in up[0].payload


@pytest.mark.asyncio
async def test_decision_v1_fills_model_versions_from_sessions():
    store = InMemoryEventStore()
    store.upcasters = default_upcaster_registry()
    ev = {
        "event_type": "DecisionGenerated",
        "event_version": 1,
        "payload": {
            "application_id": "X",
            "orchestrator_session_id": "o1",
            "recommendation": "REFER",
            "confidence": 0.5,
            "executive_summary": "s",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "contributing_sessions": ["sess-a", "sess-b"],
        },
    }
    await store.append("loan-X", [ev], expected_version=-1)
    loaded = await store.load_stream("loan-X")
    mv = loaded[0].payload.get("model_versions") or {}
    assert "sess-a" in mv and "sess-b" in mv
