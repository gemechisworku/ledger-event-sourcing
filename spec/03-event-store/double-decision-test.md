# Double-decision test (spec)

**Goal:** Two concurrent `asyncio` tasks append to the **same** `stream_id` with the **same** `expected_version`.

**Assert:**

1. Total events in stream = **initial + 1** (not +2).
2. Winner’s event has expected `stream_position`.
3. Loser receives **`OptimisticConcurrencyError`** (not swallowed).

**Maps to:** Phase 1; implement in `tests/test_event_store.py` or a dedicated concurrency test module.
