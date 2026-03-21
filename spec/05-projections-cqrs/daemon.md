# Projection daemon

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 3.

## Responsibilities

- Poll or batch-read **`events`** from `global_position > min(checkpoints)`.
- For each event, invoke **only** subscribed projection handlers.
- Update **`projection_checkpoints`** after successful processing (per projection or batch — document).
- **Fault tolerance:** on handler failure — log, optional retry counter, **skip** bad event after limit, **do not** crash the whole daemon.
- Expose **lag**: `latest_global_position - projection.last_processed`.

## Reference class shape

```python
class ProjectionDaemon:
    def __init__(self, store: EventStore, projections: list[Projection]):
        self._store = store
        self._projections = {p.name: p for p in projections}
        self._running = False

    async def run_forever(self, poll_interval_ms: int = 100) -> None:
        self._running = True
        while self._running:
            await self._process_batch()
            await asyncio.sleep(poll_interval_ms / 1000)

    async def _process_batch(self) -> None:
        # 1. min_checkpoint = min(p.last_position for p in projections)
        # 2. load_all(from_global_position=min_checkpoint, batch_size=...)
        # 3. for each event: route to projections that subscribe to event_type
        # 4. advance checkpoints after successful batch
        # 5. compute lag per projection
        ...
```

## `Projection` protocol (suggested)

Each projection defines:

- `name: str` — matches `projection_checkpoints.projection_name`
- `subscribed_event_types: set[str]` or `handles(event: StoredEvent) -> bool`
- `async def apply(self, event: StoredEvent) -> None`
- `async def get_lag(self) -> int` — ms or position delta

## `get_all_lags`

Used by **`ledger://ledger/health`** MCP resource.
