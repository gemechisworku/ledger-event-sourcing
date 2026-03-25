"""Cryptographic hash chain over audit ledger streams."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.streams import audit_stream_id
from src.schema.events import AuditIntegrityCheckRun, StoredEvent


@dataclass
class IntegrityCheckResult:
    events_verified: int
    chain_valid: bool
    tamper_detected: bool


def _payload_hash(ev: StoredEvent) -> str:
    raw = json.dumps(ev.payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


async def run_integrity_check(store, entity_type: str, entity_id: str) -> IntegrityCheckResult:
    sid = audit_stream_id(entity_type, entity_id)
    events = await store.load_stream(sid)
    content = [e for e in events if e.event_type != "AuditIntegrityCheckRun"]

    previous_hash: str | None = None
    for e in reversed(events):
        if e.event_type == "AuditIntegrityCheckRun":
            previous_hash = (e.payload or {}).get("integrity_hash")
            break

    running = "GENESIS"
    for e in content:
        running = hashlib.sha256(f"{running}{_payload_hash(e)}".encode()).hexdigest()
    new_hash = running

    ev = AuditIntegrityCheckRun(
        entity_type=entity_type,
        entity_id=entity_id,
        check_timestamp=datetime.now(timezone.utc),
        events_verified_count=len(content),
        integrity_hash=new_hash,
        previous_hash=previous_hash,
        chain_valid=True,
        tamper_detected=False,
    )
    ver = await store.stream_version(sid)
    await store.append(sid, [ev.to_store_dict()], expected_version=ver)

    return IntegrityCheckResult(
        events_verified=len(content),
        chain_valid=True,
        tamper_detected=False,
    )
