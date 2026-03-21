# Double-decision (concurrency) test

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Scenario

Two coroutines both append a **CreditAnalysisCompleted**-shaped event to the **same** `stream_id` (e.g. loan stream). Both read `stream_version == 3` and call `append(..., expected_version=3)`.

## Required assertions

| # | Assertion |
|---|-----------|
| a | Total events in that stream after both attempts = **4** (initial 3 + **one** new), not 5 |
| b | The successful append has `stream_position == 4` |
| c | The losing task raises **`OptimisticConcurrencyError`** — not swallowed, not generic `Exception` |

## Implementation notes

- Use `asyncio.create_task` or `asyncio.gather` with two concurrent `append` calls.
- Use a real Postgres `EventStore` (or test container).
- Optionally mirror the **fraud-detection** narrative: two agents racing on the same application stream.

## Files

- `tests/test_event_store.py` or dedicated `tests/test_concurrency.py`
