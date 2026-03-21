# Schema contract

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 1.

Implement as migration SQL (e.g. `ledger/schema.sql` or your migration tool). **Document every column in `DESIGN.md`.**

## `events`

```sql
CREATE TABLE events (
  event_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stream_id        TEXT NOT NULL,
  stream_position  BIGINT NOT NULL,
  global_position  BIGINT GENERATED ALWAYS AS IDENTITY,
  event_type       TEXT NOT NULL,
  event_version    SMALLINT NOT NULL DEFAULT 1,
  payload          JSONB NOT NULL,
  metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
  recorded_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_stream_position UNIQUE (stream_id, stream_position)
);

CREATE INDEX idx_events_stream_id ON events (stream_id, stream_position);
CREATE INDEX idx_events_global_pos ON events (global_position);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_events_recorded ON events (recorded_at);
```

| Column | Purpose |
|--------|---------|
| `event_id` | Stable id for outbox FK and dedup |
| `stream_id` | Logical stream (e.g. `loan-APP-001`) |
| `stream_position` | Monotonic per stream (version / ordering) |
| `global_position` | Total order for projection replay |
| `event_type` | Discriminator for `_apply` / routing |
| `event_version` | Payload schema version (upcasting) |
| `payload` | JSON event body |
| `metadata` | Correlation, causation, actor, etc. (merge `correlation_id` / `causation_id` from append here) |
| `recorded_at` | Wall-clock append time |

## `event_streams`

```sql
CREATE TABLE event_streams (
  stream_id        TEXT PRIMARY KEY,
  aggregate_type   TEXT NOT NULL,
  current_version  BIGINT NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  archived_at      TIMESTAMPTZ,
  metadata         JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

## `projection_checkpoints`

```sql
CREATE TABLE projection_checkpoints (
  projection_name  TEXT PRIMARY KEY,
  last_position    BIGINT NOT NULL DEFAULT 0,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Use **`global_position`** (or equivalent cursor) as checkpoint value — align with `load_all` ordering.

## `outbox`

```sql
CREATE TABLE outbox (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id         UUID NOT NULL REFERENCES events(event_id),
  destination      TEXT NOT NULL,
  payload          JSONB NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at     TIMESTAMPTZ,
  attempts         SMALLINT NOT NULL DEFAULT 0
);
```

**Transaction rule:** rows in `outbox` must be inserted in the **same transaction** as the corresponding `events` rows.

## Schema gaps (to consider)

- Soft-delete / GDPR — not specified; flag if needed.
- Idempotency keys on append — optional for retries.
- Partitioning `events` by time when volume grows.
