"""Cryptographic hash chain over audit ledger streams."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.streams import audit_stream_id
from src.models.events import AuditIntegrityCheckRun, StoredEvent


@dataclass
class IntegrityCheckResult:
    events_verified: int
    chain_valid: bool
    tamper_detected: bool


def _payload_hash(ev: StoredEvent) -> str:
    raw = json.dumps(ev.payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _chain_hash(business_events: list[StoredEvent]) -> str:
    running = "GENESIS"
    for e in business_events:
        running = hashlib.sha256(f"{running}{_payload_hash(e)}".encode()).hexdigest()
    return running


async def run_integrity_check(store, entity_type: str, entity_id: str) -> IntegrityCheckResult:
    sid = audit_stream_id(entity_type, entity_id)
    load_fn = getattr(store, "load_stream_persisted", None) or store.load_stream
    events = await load_fn(sid)

    business = [e for e in events if e.event_type != "AuditIntegrityCheckRun"]
    ic_runs = [e for e in events if e.event_type == "AuditIntegrityCheckRun"]

    new_hash = _chain_hash(business)
    tamper_detected = False
    chain_valid = True

    if ic_runs:
        last_ic = ic_runs[-1]
        lp = last_ic.payload or {}
        prev_n = int(lp.get("events_verified_count") or 0)
        prev_hash = str(lp.get("integrity_hash") or "")
        if prev_n == len(business) and prev_hash and new_hash != prev_hash:
            tamper_detected = True
            chain_valid = False

    ev = AuditIntegrityCheckRun(
        entity_type=entity_type,
        entity_id=entity_id,
        check_timestamp=datetime.now(timezone.utc),
        events_verified_count=len(business),
        integrity_hash=new_hash,
        previous_hash=ic_runs[-1].payload.get("integrity_hash") if ic_runs else None,
        chain_valid=chain_valid,
        tamper_detected=tamper_detected,
    )
    ver = await store.stream_version(sid)
    await store.append(sid, [ev.to_store_dict()], expected_version=ver)

    return IntegrityCheckResult(
        events_verified=len(business),
        chain_valid=chain_valid,
        tamper_detected=tamper_detected,
    )
