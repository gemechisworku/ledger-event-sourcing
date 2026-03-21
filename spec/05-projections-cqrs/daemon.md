# Projection daemon

## Responsibilities

- Read from global event order (`load_all` or equivalent) from min checkpoint.
- Route each event to subscribed projections; update `projection_checkpoints` after successful batches.
- On handler failure: log, optional retry limit, **do not** halt entire daemon.
- Expose **per-projection lag** (global position vs last processed).

## Implementation

Asyncio polling pattern; align with `ledger/event_store.py` once `load_all` exists.
