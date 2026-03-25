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
