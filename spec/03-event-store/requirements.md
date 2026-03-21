# EventStore — functional requirements

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)  
**Implementation:** `src/event_store.py`

## `append`

```python
async def append(
    self,
    stream_id: str,
    events: list[BaseEvent],
    expected_version: int,  # -1 = new stream only; N = stream must be exactly at N
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> int:
    """Return new stream version after append.

    Atomically:
    - Enforce optimistic concurrency vs event_streams.current_version
    - Insert one row per event with sequential stream_position
    - Assign monotonic global_position
    - Update event_streams.current_version
    - Insert outbox row(s) per policy (often one per event or batched)

    Raises OptimisticConcurrencyError if actual version != expected_version.
    """
```

**Semantics:**

- `expected_version == -1`: stream must not exist **or** be empty (define whether empty stream exists as row with version 0).
- `expected_version >= 0`: `event_streams.current_version` must equal `expected_version` before append.
- Persist `correlation_id` / `causation_id` into `metadata` JSON (or dedicated columns if you add them — justify in `DESIGN.md`).

## `load_stream`

```python
async def load_stream(
    self,
    stream_id: str,
    from_position: int = 0,
    to_position: int | None = None,
) -> list[StoredEvent]:
    """Events in stream order. Apply upcasters on read path."""
```

## `load_all`

```python
async def load_all(
    self,
    from_global_position: int = 0,
    event_types: list[str] | None = None,
    batch_size: int = 500,
) -> AsyncIterator[StoredEvent]:
    """Async generator for global replay (projections)."""
```

## Other methods

```python
async def stream_version(self, stream_id: str) -> int
async def archive_stream(self, stream_id: str) -> None
async def get_stream_metadata(self, stream_id: str) -> StreamMetadata
```

## Types

- `BaseEvent` — Pydantic; `src/schema/events.py`
- `StoredEvent` — persisted envelope: `event_id`, `stream_id`, `stream_position`, `global_position`, `event_type`, `event_version`, `payload`, `metadata`, `recorded_at`
- `OptimisticConcurrencyError`, `DomainError` — custom exceptions

## Outbox policy

- Minimum: insert one outbox row per appended event with `destination` TBD (e.g. `kafka:loan-events`).
- Publisher process is **out of scope** for core store but table must exist for transactional guarantee.

## Integration with registry

- `aggregate_type` on `event_streams` should be set on first append (derive from stream prefix or caller).
