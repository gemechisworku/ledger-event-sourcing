# Schema contract

Reference tables:

- `events` — `event_id`, `stream_id`, `stream_position`, `global_position` (identity), `event_type`, `event_version`, `payload`, `metadata`, `recorded_at`, unique `(stream_id, stream_position)`.
- `event_streams` — stream metadata + `current_version`.
- `projection_checkpoints` — daemon watermarks.
- `outbox` — transactional outbox for downstream publish.

Indexes per DDL in `ref_docs/requirements.md` / `DESIGN.md`.

**Documentation:** justify each column in **`DESIGN.md`**; keep one-line rationale here when stable.
