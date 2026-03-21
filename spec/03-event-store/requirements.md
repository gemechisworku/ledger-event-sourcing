# EventStore requirements

## Interface

- Async **`append(stream_id, events, expected_version, correlation_id?, causation_id?)`** → new version; **`OptimisticConcurrencyError`** on mismatch.
- **`load_stream`** / **`load_all`** (async iterator, batching); **`stream_version`**, **`archive_stream`**, **`get_stream_metadata`**.
- **Outbox:** append writes events + outbox rows in **one transaction**.

## Repo

- Implement `ledger/event_store.py` with Postgres.
- Align event types with `ledger/schema/events.py` (`BaseEvent`, etc.).

## Open points

- How `metadata` JSON is populated (actor, schema version, etc.).
- Idempotency / deduplication policy if any.
