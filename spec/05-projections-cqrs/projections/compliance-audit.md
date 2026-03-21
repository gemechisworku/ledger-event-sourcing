# Projection: ComplianceAuditView

**Must support:**

- `get_current_compliance(application_id)`
- `get_compliance_at(application_id, timestamp)` — regulatory time travel
- `get_projection_lag()`
- `rebuild_from_scratch()` without blocking readers — document strategy

**Snapshot strategy:** justify in `DESIGN.md`; outline options here (event-count vs time vs manual).
