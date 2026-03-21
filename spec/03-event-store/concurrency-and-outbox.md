# Concurrency & outbox

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Optimistic concurrency

- **`expected_version = -1`:** create stream / first append (define interaction with `event_streams` row).
- **`expected_version = N`:** `current_version` must equal **N** before append; next positions are N+1, N+2, … for batch.
- On mismatch → **`OptimisticConcurrencyError`** with `expected_version`, `actual_version`, `stream_id`.

## Why it matters (domain)

Two fraud agents racing on the same loan stream: without OCC both append; state is inconsistent. With OCC, one wins; the other reloads and reconciles.

## Outbox

- Insert **`outbox`** rows in the **same** DB transaction as **`events`**.
- Publisher worker marks `published_at`, increments `attempts` on failure.
- `destination` + `payload` shape are integration contracts (Kafka topic, etc.).

## Metadata

- Merge **`correlation_id`** / **`causation_id`** from `append()` into `events.metadata` JSON for downstream tracing and Phase 6 causal queries.
