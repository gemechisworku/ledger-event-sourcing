-- Ledger event store schema (PostgreSQL)
-- Apply once per database: psql $DATABASE_URL -f src/schema.sql
--
-- Four read patterns supported (each has a dedicated index):
--   1. Stream replay   — load_stream(stream_id, from_position)
--   2. Global catchup  — load_all(from_position, event_types?)
--   3. Type projection — load_all filtered by event_type(s) + global ordering
--   4. Time-range      — query events within a recorded_at window

CREATE TABLE IF NOT EXISTS events (
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

-- Read pattern 1: stream replay — WHERE stream_id = $1 ORDER BY stream_position
CREATE INDEX IF NOT EXISTS idx_events_stream_id
  ON events (stream_id, stream_position);

-- Read pattern 2: global catchup — WHERE global_position > $1 ORDER BY global_position
CREATE INDEX IF NOT EXISTS idx_events_global_pos
  ON events (global_position);

-- Read pattern 3: type-filtered projection — WHERE event_type = ANY($1) AND global_position > $2
CREATE INDEX IF NOT EXISTS idx_events_type_global
  ON events (event_type, global_position);

-- Read pattern 4: time-range queries — WHERE recorded_at BETWEEN $1 AND $2
CREATE INDEX IF NOT EXISTS idx_events_recorded_range
  ON events (recorded_at, stream_id);

CREATE TABLE IF NOT EXISTS event_streams (
  stream_id        TEXT PRIMARY KEY,
  aggregate_type   TEXT NOT NULL,
  current_version  BIGINT NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  archived_at      TIMESTAMPTZ,
  metadata         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS projection_checkpoints (
  projection_name  TEXT PRIMARY KEY,
  last_position    BIGINT NOT NULL DEFAULT 0,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outbox (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id         UUID NOT NULL,
  destination      TEXT NOT NULL,
  payload          JSONB NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at     TIMESTAMPTZ,
  attempts         SMALLINT NOT NULL DEFAULT 0,
  CONSTRAINT fk_outbox_event
    FOREIGN KEY (event_id) REFERENCES events (event_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
  ON outbox (created_at) WHERE published_at IS NULL;
