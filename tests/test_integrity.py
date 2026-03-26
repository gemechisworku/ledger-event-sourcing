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


@pytest.mark.asyncio
async def test_tamper_detected_when_payload_mutated_in_store():
    """Same event count as last check but hash mismatch → tamper_detected."""
    store = InMemoryEventStore()
    await store.append(
        "audit-loan-TAMP",
        [
            {
                "event_type": "AuditNote",
                "event_version": 1,
                "payload": {"note": "clean"},
            }
        ],
        expected_version=-1,
    )
    r1 = await run_integrity_check(store, "loan", "TAMP")
    assert r1.tamper_detected is False

    sid = "audit-loan-TAMP"
    lst = store._streams[sid]
    idx = next(i for i, e in enumerate(lst) if e.event_type == "AuditNote")
    old = lst[idx]
    tampered = old.model_copy(update={"payload": {"note": "dirty"}})
    lst[idx] = tampered
    for i, g in enumerate(store._global):
        if g.event_id == old.event_id:
            store._global[i] = tampered
            break

    r2 = await run_integrity_check(store, "loan", "TAMP")
    assert r2.tamper_detected is True
    assert r2.chain_valid is False
