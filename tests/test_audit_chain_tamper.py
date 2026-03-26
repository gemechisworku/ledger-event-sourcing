"""Demonstrate that mutating payload bytes changes the cumulative chain digest (audit_chain semantics)."""
from __future__ import annotations

import hashlib
import json

from src.integrity.audit_chain import _payload_hash
from src.schema.events import StoredEvent


def _running_chain(events: list[StoredEvent]) -> str:
    running = "GENESIS"
    for e in events:
        running = hashlib.sha256(f"{running}{_payload_hash(e)}".encode()).hexdigest()
    return running


def test_tampered_payload_changes_chain_digest():
    """Same events with one payload tweak → different chain end state (tamper detection signal)."""
    base = StoredEvent(
        event_id="00000000-0000-0000-0000-000000000001",
        stream_id="audit-loan-X",
        stream_position=1,
        global_position=1,
        event_type="SomeAuditEvent",
        event_version=1,
        payload={"k": "v"},
        metadata={},
        recorded_at="2026-01-01T00:00:00+00:00",
    )
    h_clean = _running_chain([base])

    tampered = StoredEvent(
        event_id=base.event_id,
        stream_id=base.stream_id,
        stream_position=base.stream_position,
        global_position=base.global_position,
        event_type=base.event_type,
        event_version=base.event_version,
        payload={"k": "tampered"},
        metadata=base.metadata,
        recorded_at=base.recorded_at,
    )
    h_tampered = _running_chain([tampered])

    assert h_clean != h_tampered
    assert json.dumps(base.payload, sort_keys=True) != json.dumps(tampered.payload, sort_keys=True)
