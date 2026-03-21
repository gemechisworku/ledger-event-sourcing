# Non-functional constraints

- **Database:** PostgreSQL — reference schema: `events`, `event_streams`, `projection_checkpoints`, `outbox` (see `03-event-store/schema-contract.md`).
- **Python:** async I/O; `uv` + `asyncpg` per `pyproject.toml`.
- **SLOs:** e.g. ApplicationSummary lag &lt; 500ms; ComplianceAuditView up to ~2s — refine in `05-projections-cqrs/slo-and-lag.md`.

Add deployment notes (Docker ports, `.env`) when they affect design.
