"""Audit chain integrity."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.event_store import InMemoryEventStore
from src.integrity.audit_chain import run_integrity_check


@pytest.mark.asyncio
async def test_run_integrity_check_appends():
    store = InMemoryEventStore()
    r = await run_integrity_check(store, "loan", "APP-99")
    assert r.events_verified == 0
    stream = await store.load_stream("audit-loan-APP-99")
    assert len(stream) == 1
    assert stream[0].event_type == "AuditIntegrityCheckRun"
