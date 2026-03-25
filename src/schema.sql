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

-- ─── Read models (Phase 4 projections) ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS projection_application_summary (
  application_id            TEXT PRIMARY KEY,
  state                     TEXT NOT NULL DEFAULT 'UNKNOWN',
  applicant_id              TEXT,
  requested_amount_usd      NUMERIC,
  approved_amount_usd       NUMERIC,
  risk_tier                 TEXT,
  fraud_score               DOUBLE PRECISION,
  compliance_status         TEXT,
  decision                  TEXT,
  agent_sessions_completed  JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_event_type           TEXT,
  last_event_at             TIMESTAMPTZ,
  human_reviewer_id         TEXT,
  final_decision_at         TIMESTAMPTZ,
  last_global_position      BIGINT NOT NULL DEFAULT 0,
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projection_agent_performance (
  agent_id              TEXT NOT NULL,
  model_version         TEXT NOT NULL,
  analyses_completed    INTEGER NOT NULL DEFAULT 0,
  decisions_generated   INTEGER NOT NULL DEFAULT 0,
  avg_confidence_score  DOUBLE PRECISION,
  avg_duration_ms       DOUBLE PRECISION,
  approve_rate          DOUBLE PRECISION,
  decline_rate          DOUBLE PRECISION,
  refer_rate            DOUBLE PRECISION,
  human_override_rate   DOUBLE PRECISION,
  first_seen_at         TIMESTAMPTZ,
  last_seen_at          TIMESTAMPTZ,
  samples_confidence    INTEGER NOT NULL DEFAULT 0,
  samples_duration_ms   INTEGER NOT NULL DEFAULT 0,
  samples_decisions     INTEGER NOT NULL DEFAULT 0,
  counts_approve        INTEGER NOT NULL DEFAULT 0,
  counts_decline        INTEGER NOT NULL DEFAULT 0,
  counts_refer          INTEGER NOT NULL DEFAULT 0,
  counts_override       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (agent_id, model_version)
);

CREATE TABLE IF NOT EXISTS projection_compliance_audit (
  application_id         TEXT PRIMARY KEY,
  overall_verdict        TEXT,
  rules_json             JSONB NOT NULL DEFAULT '[]'::jsonb,
  regulation_set_version TEXT,
  last_global_position   BIGINT NOT NULL DEFAULT 0,
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
