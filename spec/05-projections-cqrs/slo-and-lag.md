# SLOs & lag

Exemplar targets:

- **ApplicationSummary:** lag &lt; 500ms under normal conditions.
- **ComplianceAuditView:** up to ~2s lag.

**Tests:** simulated load (e.g. 50 concurrent command handlers) — document how lag is measured (`ProjectionDaemon.get_lag` / `get_all_lags`).
