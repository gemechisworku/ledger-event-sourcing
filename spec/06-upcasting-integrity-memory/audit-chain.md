# Cryptographic audit chain

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 4B.

## Scope

Hash chain over **`AuditLedger`** stream: `audit-{entity_type}-{entity_id}`.

Each **`AuditIntegrityCheckRun`** stores:

- `integrity_hash` — over preceding events + prior hash
- `previous_hash` — chain link
- `events_verified_count`, `check_timestamp`, `entity_id`

## `run_integrity_check`

```python
async def run_integrity_check(
    store: EventStore,
    entity_type: str,
    entity_id: str,
) -> IntegrityCheckResult:
    """
    1. Load all events for the entity's primary stream (or audit stream as defined)
    2. Load last AuditIntegrityCheckRun if any
    3. Hash payloads of events since last check
    4. new_hash = sha256(previous_hash + concatenated_event_hashes)
    5. Append AuditIntegrityCheckRun to audit-{entity_type}-{entity_id}
    6. Return IntegrityCheckResult(events_verified, chain_valid, tamper_detected)
    """
```

## Return type

- `events_verified: int`
- `chain_valid: bool`
- `tamper_detected: bool`
